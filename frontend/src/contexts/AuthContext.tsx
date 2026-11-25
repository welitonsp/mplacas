import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { configureApi } from '../lib/api'
import { TokenStore } from '../lib/auth'
import {
  adoptAccessToken,
  announceSessionChange,
  authFetch,
  markSessionChanged,
  openSession,
  refreshSession,
  revokeSession,
  RequestTimeoutError,
  subscribeSessionChanges,
} from '../lib/session'
import { SELECTED_PLANT_STORAGE_KEY } from './PlantContext'
import { safeStorage } from '../lib/storage'

// Estado da sessão nesta aba (ADR-102):
// - `checking`: perguntando ao servidor se o cookie da sessão ainda vale;
// - `authenticated`: há access token em memória;
// - `unauthenticated`: o servidor disse que não há sessão (vai ao login);
// - `unreachable`: não deu para perguntar (rede, servidor acordando) — a
//   sessão pode estar viva, então oferece "Tentar de novo", nunca o login.
export type SessionStatus = 'checking' | 'authenticated' | 'unauthenticated' | 'unreachable'

interface AuthContextValue {
  status: SessionStatus
  isAuthenticated: boolean
  username: string | null
  // Verdadeiro só se esta aba teve sessão e o servidor a encerrou (refresh
  // recusado). Em memória, nunca persistido; logout voluntário não liga.
  sessionEnded: boolean
  login: (username: string, password: string) => Promise<void>
  // Atualiza o estado React depois de uma sessão aberta fora do `login`
  // (aceite de convite, ADR-093). O token já foi gravado por
  // `adoptAccessToken` dentro do `openSession`; o refresh token ficou no
  // cookie HttpOnly.
  adoptSession: (username: string) => void
  // Encerra no servidor a sessão atual antes de abrir outra (aceite de convite
  // com alguém já logado nesta aba/navegador).
  endServerSession: () => Promise<void>
  // Pergunta de novo ao servidor depois de `unreachable`.
  retrySession: () => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readAccessToken(payload: unknown): string | null {
  const token = (payload as { access_token?: unknown } | null)?.access_token
  return typeof token === 'string' && token !== '' ? token : null
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>(() => (TokenStore.get() ? 'authenticated' : 'checking'))
  // Em memória — nunca persistido, nunca derivado de decodificação do JWT.
  const [username, setUsername] = useState<string | null>(null)
  const [sessionEnded, setSessionEnded] = useState(false)
  // Cada mudança de sessão (login, convite, logout, expiração, nova checagem)
  // incrementa a geração; um resultado de checagem de uma geração antiga é
  // descartado e nunca sobrescreve um login feito enquanto ela rodava.
  const generationRef = useRef(0)

  const checkSession = useCallback(() => {
    const generation = ++generationRef.current
    setStatus('checking')
    void refreshSession().then((outcome) => {
      if (generation !== generationRef.current || outcome.kind === 'superseded') return
      if (outcome.kind === 'ok') setStatus('authenticated')
      else setStatus(outcome.kind)
    })
  }, [])

  // Ao carregar o app (F5, link direto, aba nova) sem token em memória,
  // pergunta ao servidor pelo cookie ANTES de qualquer rota protegida decidir
  // mandar ao login.
  useEffect(() => {
    if (!TokenStore.get()) checkSession()
  }, [checkSession])

  // Limpeza local da sessão, sem mexer em `sessionEnded` (quem chama decide).
  // Não fala com o servidor: a expiração usa só isto, porque um logout no
  // servidor ali poderia revogar o token novo que outra aba acabou de receber.
  const clearLocal = useCallback(() => {
    generationRef.current += 1
    // Descarta qualquer refresh em voo: a resposta dele não grava mais nada.
    markSessionChanged()
    TokenStore.clear()
    // A usina selecionada é estado de sessão (ADR-069, seção 5) — limpa junto
    // do token para não vazar seleção entre logins diferentes no navegador.
    safeStorage.remove(SELECTED_PLANT_STORAGE_KEY)
    setStatus('unauthenticated')
    setUsername(null)
  }, [])

  // Logout voluntário: limpa local, avisa as outras abas e revoga no servidor
  // (apaga o cookie).
  const logout = useCallback(() => {
    clearLocal()
    setSessionEnded(false)
    announceSessionChange()
    void revokeSession()
  }, [clearLocal])

  // Outra aba entrou (talvez como outra pessoa), aceitou convite ou saiu: o
  // cookie mudou para todas. Esta aba larga o que tinha e vai ao login (a rota
  // protegida guarda `state.from`), sem o aviso de "sessão encerrada".
  useEffect(
    () =>
      subscribeSessionChanges(() => {
        clearLocal()
        setSessionEnded(false)
      }),
    [clearLocal],
  )

  // Chamado pelo api.ts quando a renovação é recusada: a sessão acabou sem o
  // usuário pedir. Vários 401 simultâneos compartilham a mesma renovação e
  // chamam isto em sequência: só a primeira encontra token.
  const expireSession = useCallback(() => {
    if (!TokenStore.get()) return
    clearLocal()
    setSessionEnded(true)
  }, [clearLocal])

  configureApi(expireSession)

  const login = useCallback(async (name: string, password: string) => {
    // Atrás de qualquer refresh em voo e do lock (ver `openSession`): a
    // resposta de um refresh da sessão anterior nunca chega depois desta.
    await openSession(async () => {
      let response: Response
      try {
        response = await authFetch('/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: name, password }),
        })
      } catch (error) {
        // Prazo esgotado e falha de conexão pedem ações diferentes: no primeiro
        // caso o servidor provavelmente está acordando (plano grátis); no
        // segundo, a rede do usuário ou o servidor estão fora.
        if (error instanceof RequestTimeoutError) {
          throw new Error(
            'O servidor não respondeu a tempo. Ele pode estar iniciando — aguarde um minuto e tente novamente.',
          )
        }
        throw new Error(
          'Não foi possível conectar ao servidor. Verifique sua internet e tente novamente em instantes.',
        )
      }

      if (!response.ok) {
        const code = response.status
        if (code === 401) throw new Error('Credenciais inválidas.')
        if (code === 429) throw new Error('Muitas tentativas. Aguarde e tente novamente.')
        // Todo 5xx é falha nossa (incidente de 2026-08-21): a mensagem não pode
        // mandar repetir nem sugerir que o problema é a senha.
        if (code >= 500) {
          throw new Error(
            'O sistema está indisponível no momento. Não é a sua senha — a falha é nossa. Tente mais tarde.',
          )
        }
        throw new Error('Erro ao autenticar. Tente novamente.')
      }

      // Só o access token é lido; o refresh token que o corpo ainda traz
      // (transitório no backend) é ignorado — a sessão persistente é o cookie.
      const accessToken = readAccessToken(await response.json().catch(() => null))
      if (accessToken === null) throw new Error('Erro ao autenticar. Tente novamente.')

      // Ainda dentro do lock: nova época (descarta refresh antigo) e o token.
      adoptAccessToken(accessToken)
    })

    generationRef.current += 1
    setStatus('authenticated')
    setSessionEnded(false)
    setUsername(name)
    announceSessionChange()
  }, [])

  const adoptSession = useCallback((name: string) => {
    generationRef.current += 1
    safeStorage.remove(SELECTED_PLANT_STORAGE_KEY)
    setStatus('authenticated')
    setSessionEnded(false)
    setUsername(name)
    announceSessionChange()
  }, [])

  const endServerSession = useCallback(() => revokeSession(), [])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      isAuthenticated: status === 'authenticated',
      username,
      sessionEnded,
      login,
      adoptSession,
      endServerSession,
      retrySession: checkSession,
      logout,
    }),
    [status, username, sessionEnded, login, adoptSession, endServerSession, checkSession, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
