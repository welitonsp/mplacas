import React, { createContext, useCallback, useContext, useRef, useState } from 'react'
import { AUTH_TIMEOUT_MS, configureApi, apiFetch, withTimeout } from '../lib/api'
import { TokenStore } from '../lib/auth'
import { API_URL } from '../env'
import { SELECTED_PLANT_STORAGE_KEY } from './PlantContext'
import { safeStorage } from '../lib/storage'

interface AuthContextValue {
  isAuthenticated: boolean
  username: string | null
  // Verdadeiro só se esta aba teve sessão e o servidor a encerrou (refresh
  // recusado). Em memória, nunca persistido; logout voluntário não liga.
  sessionEnded: boolean
  login: (username: string, password: string) => Promise<void>
  // Entra com a sessão que o servidor acabou de abrir (aceite de convite,
  // ADR-093): os tokens ficam só em memória, como no login.
  adoptSession: (accessToken: string, refreshToken: string, username: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!TokenStore.get())
  // Em memória, mesma vida útil de `refreshTokenRef` abaixo — nunca persistido
  // em armazenamento do navegador, nunca derivado de decodificação do JWT.
  const [username, setUsername] = useState<string | null>(null)
  const refreshTokenRef = useRef<string | null>(null)
  const [sessionEnded, setSessionEnded] = useState(false)

  // Limpeza da sessão sem mexer em `sessionEnded` (quem chama decide o flag).
  const clearSession = useCallback(() => {
    const refreshToken = refreshTokenRef.current
    TokenStore.clear()
    // A usina selecionada é estado de sessão (ADR-069, seção 5) — limpa junto
    // do token para não vazar seleção entre logins de usuários diferentes no
    // mesmo navegador.
    safeStorage.remove(SELECTED_PLANT_STORAGE_KEY)
    refreshTokenRef.current = null
    setIsAuthenticated(false)
    setUsername(null)

    if (refreshToken) {
      void fetch(`${API_URL}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
        keepalive: true,
      }).catch(() => undefined)
    }
  }, [])

  const logout = useCallback(() => {
    clearSession()
    setSessionEnded(false)
  }, [clearSession])

  const getRefreshToken = useCallback(() => refreshTokenRef.current, [])
  const setRefreshToken = useCallback((token: string) => {
    refreshTokenRef.current = token
  }, [])

  // Chamado pelo api.ts quando a renovação é recusada: a sessão acabou sem o
  // usuário pedir. Só conta se havia sessão nesta aba.
  const expireSession = useCallback(() => {
    // Vários 401 simultâneos compartilham o mesmo refresh recusado e chamam
    // isto em sequência: só a primeira encontra sessão; as demais não fazem nada.
    const hadSession = !!TokenStore.get() || refreshTokenRef.current !== null
    if (!hadSession) return
    clearSession()
    setSessionEnded(true)
  }, [clearSession])

  // Configura o api.ts com as funções do contexto.
  configureApi(getRefreshToken, setRefreshToken, expireSession)

  const login = useCallback(async (username: string, password: string) => {
    // Prazo de autenticação (auditoria v6, A-03): sem ele, um servidor que
    // aceita a conexão e não responde deixava o botão em "Entrando..." para
    // sempre, sem erro e sem saída — o pior estado possível numa tela de
    // login, porque o usuário não sabe se deve esperar ou tentar de novo.
    const deadline = withTimeout(AUTH_TIMEOUT_MS)
    let response: Response
    try {
      response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
        signal: deadline.signal,
      })
    } catch {
      // Prazo esgotado e falha de conexão pedem ações diferentes: no primeiro
      // caso o servidor provavelmente está acordando (plano grátis); no
      // segundo, a rede do usuário ou o servidor estão fora. Respostas 5xx não
      // caem mais aqui — a API passou a devolvê-las com CORS (2026-10-13).
      if (deadline.timedOut()) {
        throw new Error(
          'O servidor não respondeu a tempo. Ele pode estar iniciando — aguarde um minuto e tente novamente.',
        )
      }
      throw new Error(
        'Não foi possível conectar ao servidor. Verifique sua internet e tente novamente em instantes.',
      )
    } finally {
      deadline.clear()
    }

    if (!response.ok) {
      const status = response.status
      if (status === 401) throw new Error('Credenciais inválidas.')
      if (status === 429) throw new Error('Muitas tentativas. Aguarde e tente novamente.')
      // Falha do lado do servidor (incidente de 2026-08-21): o banco recusou
      // conexão por cota esgotada e /auth/login passou a devolver 500. A
      // mensagem antiga para 5xx era "Erro ao autenticar. Tente novamente.",
      // que mandava o usuário repetir uma ação que não podia dar certo por
      // dias, e sugeria que o problema era a senha dele. Todo 5xx é falha
      // nossa, e a mensagem tem que dizer isso — sem prometer que a próxima
      // tentativa resolve.
      if (status >= 500) {
        throw new Error(
          'O sistema está indisponível no momento. Não é a sua senha — a falha é nossa. Tente mais tarde.',
        )
      }
      throw new Error('Erro ao autenticar. Tente novamente.')
    }

    const { access_token, refresh_token } = await response.json() as {
      access_token: string
      refresh_token: string
    }

    TokenStore.set(access_token)
    refreshTokenRef.current = refresh_token
    setIsAuthenticated(true)
    setSessionEnded(false)
    setUsername(username)
  }, [])

  const adoptSession = useCallback((accessToken: string, refreshToken: string, name: string) => {
    // Mesma limpeza do logout para a sessão anterior desta aba (ex.: o dono
    // testando o próprio convite): seleção de usina e refresh token antigos.
    const previous = refreshTokenRef.current
    if (previous && previous !== refreshToken) {
      void fetch(`${API_URL}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: previous }),
        keepalive: true,
      }).catch(() => undefined)
    }
    safeStorage.remove(SELECTED_PLANT_STORAGE_KEY)
    TokenStore.set(accessToken)
    refreshTokenRef.current = refreshToken
    setIsAuthenticated(true)
    setSessionEnded(false)
    setUsername(name)
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, username, sessionEnded, login, adoptSession, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

// Re-export apiFetch so pages can import from a single auth module if desired
export { apiFetch }
