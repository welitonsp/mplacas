import { API_URL } from '../env'
import { TokenStore } from './auth'

// Transporte da sessão (ADR-102). O refresh token mora num cookie
// `__Secure-mplacas_rt` HttpOnly gravado pelo backend em `Path=/api/auth`: este
// código nunca o lê, nunca o recebe e nunca o envia por conta própria — quem o
// anexa é o navegador, porque a API agora é a própria origem do site (proxy
// `/api/*` da Cloudflare Pages Function). O access token continua só em
// memória (`TokenStore`).

// Timeout de rede (auditoria v6, achado A-03). Nenhuma chamada tinha limite:
// uma conexão que abre e nunca responde deixava a interface em "carregando"
// para sempre. Desde o Render no plano grátis (ADR-076) a API hiberna e a
// primeira requisição leva de 30 a 60 s; o proxy corta em 58 s com 504, antes
// deste prazo, para o cliente receber uma resposta clara em vez de abortar.
export const AUTH_TIMEOUT_MS = 60_000
export const DATA_TIMEOUT_MS = 60_000

// Combina o prazo interno com um `AbortController` externo (desmontagem de
// componente, troca de usina). O `clear` evita que o timer sobreviva à resposta.
export function withTimeout(
  timeoutMs: number,
  externalSignal?: AbortSignal | null
): { signal: AbortSignal; clear: () => void; timedOut: () => boolean } {
  const controller = new AbortController()
  let expired = false

  const timer = setTimeout(() => {
    expired = true
    controller.abort()
  }, timeoutMs)

  const forward = () => controller.abort()
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort()
    else externalSignal.addEventListener('abort', forward, { once: true })
  }

  return {
    signal: controller.signal,
    clear: () => {
      clearTimeout(timer)
      externalSignal?.removeEventListener('abort', forward)
    },
    timedOut: () => expired,
  }
}

// "Servidor demorou demais" é diferente de "servidor recusou" e de "usuário
// saiu da tela": as três pedem mensagens e ações diferentes.
export class RequestTimeoutError extends Error {
  constructor(path: string, timeoutMs: number) {
    super(`A requisição para ${path} excedeu ${timeoutMs}ms.`)
    this.name = 'RequestTimeoutError'
  }
}

// Pedido de autenticação (login, refresh, logout, convite):
// - `credentials: 'same-origin'`: o cookie da sessão só viaja para a própria
//   origem;
// - `X-Mplacas-Auth: 1`: metade da defesa CSRF do backend;
// - `referrerPolicy: 'same-origin'`: a página inteira usa `no-referrer`
//   (`_headers`), e com ela o navegador manda `Origin: null` até em POST para a
//   própria origem — o backend recusa `Origin: null` (403). Por pedido, esta
//   política mantém o `Origin` real; o `Referer` só iria para a própria origem
//   e o proxy não o repassa.
export function authRequestInit(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers)
  headers.set('X-Mplacas-Auth', '1')
  return { ...init, headers, credentials: 'same-origin', referrerPolicy: 'same-origin', cache: 'no-store' }
}

// Pedido de autenticação com prazo. Prazo esgotado vira `RequestTimeoutError`;
// falha de rede propaga o erro original.
export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const deadline = withTimeout(AUTH_TIMEOUT_MS)
  try {
    return await fetch(`${API_URL}${path}`, { ...authRequestInit(init), signal: deadline.signal })
  } catch (error) {
    if (deadline.timedOut()) throw new RequestTimeoutError(path, AUTH_TIMEOUT_MS)
    throw error
  } finally {
    deadline.clear()
  }
}

export type RefreshOutcome =
  | { kind: 'ok'; accessToken: string }
  // Sem sessão válida (401, cookie ausente, 4xx, 200 malformado): vai ao login.
  | { kind: 'unauthenticated' }
  // Não deu para saber (rede, prazo, 5xx do proxy/servidor): NÃO manda ao
  // login — a sessão pode estar viva e o servidor só acordando.
  | { kind: 'unreachable' }

// Duas abas pedindo refresh juntas: o backend tolera a perdedora por 10 s
// respondendo 401 sem apagar o cookie (ADR-102 § 4). Repetimos uma vez, depois
// de dar tempo à resposta da vencedora gravar o cookie novo.
export const REFRESH_RETRY_DELAY_MS = 300

async function refreshOnce(): Promise<RefreshOutcome | 401> {
  let response: Response
  try {
    // Sem corpo: a credencial é o cookie.
    response = await authFetch('/auth/refresh', { method: 'POST' })
  } catch {
    return { kind: 'unreachable' }
  }
  if (response.status === 401) return 401
  if (response.status >= 500 || response.status === 408 || response.status === 429) {
    return { kind: 'unreachable' }
  }
  if (!response.ok) return { kind: 'unauthenticated' }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    return { kind: 'unauthenticated' }
  }
  // Validação em runtime: um 200 malformado não pode gravar lixo no
  // `TokenStore`. O refresh token que o corpo ainda traz (transitório no backend) é
  // ignorado de propósito: não é lido nem guardado.
  const accessToken = (payload as { access_token?: unknown } | null)?.access_token
  if (typeof accessToken !== 'string' || accessToken === '') return { kind: 'unauthenticated' }
  TokenStore.set(accessToken)
  return { kind: 'ok', accessToken }
}

async function refreshWithRetry(): Promise<RefreshOutcome> {
  const first = await refreshOnce()
  if (first !== 401) return first
  await new Promise((resolve) => setTimeout(resolve, REFRESH_RETRY_DELAY_MS))
  const second = await refreshOnce()
  return second === 401 ? { kind: 'unauthenticated' } : second
}

// Serializa entre abas com a Web Locks API: a segunda aba só pede o refresh
// depois que a primeira recebeu a resposta (e o navegador gravou o cookie
// rotacionado). Sem suporte, vale só o single-flight dentro da aba.
export const REFRESH_LOCK_NAME = 'mplacas-refresh'

function withRefreshLock<T>(task: () => Promise<T>): Promise<T> {
  const locks = typeof navigator === 'undefined' ? undefined : navigator.locks
  if (!locks || typeof locks.request !== 'function') return task()
  return locks.request(REFRESH_LOCK_NAME, task) as Promise<T>
}

// Single-flight dentro da aba (A-02): requisições concorrentes compartilham a
// mesma renovação. O `finally` limpa a referência mesmo em falha.
let refreshInFlight: Promise<RefreshOutcome> | null = null

export function refreshSession(): Promise<RefreshOutcome> {
  if (refreshInFlight === null) {
    refreshInFlight = withRefreshLock(refreshWithRetry)
      .catch((): RefreshOutcome => ({ kind: 'unreachable' }))
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

// Encerra a sessão no servidor: revoga e apaga o cookie. Melhor esforço — falha
// de rede não restaura nada localmente. `keepalive` deixa o pedido terminar
// mesmo se a aba fechar logo em seguida. Passa pelo mesmo lock do refresh para
// não cruzar com uma rotação de outra aba.
export function revokeSession(): Promise<void> {
  return withRefreshLock(() =>
    fetch(`${API_URL}/auth/logout`, authRequestInit({ method: 'POST', keepalive: true }))
  ).then(
    () => undefined,
    () => undefined
  )
}
