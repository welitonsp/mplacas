import { API_URL } from '../env'
import { TokenStore } from './auth'
import { safeStorage } from './storage'

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
  // A sessão desta aba mudou (login, convite, logout, expiração) enquanto o
  // refresh rodava: a resposta é de outra identidade/sessão e foi descartada.
  // Quem pediu não grava nada e não repete a requisição.
  | { kind: 'superseded' }

// Época da sessão nesta aba. Muda a cada login, adoção de sessão (convite),
// logout e expiração. Um refresh captura a época quando é pedido; se ela mudou
// até a resposta chegar, o token recebido é descartado. Sem isto, num
// computador compartilhado com o cookie de A, o refresh atrasado de A (Render
// acordando) chegaria depois do login de B e a tela "de B" mostraria dados de A;
// e um refresh em voo durante o logout deixaria um JWT válido na memória.
let sessionEpoch = 0

export function markSessionChanged(): void {
  sessionEpoch += 1
}

// Grava o access token de uma sessão que acabou de abrir (login, aceite de
// convite). Chamar DENTRO da task de `openSession`, para época e token mudarem
// ainda atrás do lock.
export function adoptAccessToken(accessToken: string): void {
  markSessionChanged()
  TokenStore.set(accessToken)
}

// Aviso entre abas de que a sessão do navegador mudou (login, convite, logout).
// O cookie é um só para todas as abas: se a aba 1 entra como B, o próximo
// refresh da aba 2 (que mostra A) receberia o token de B. Ao receber o aviso,
// as outras abas limpam o estado local e vão ao login.
//
// Canal: `BroadcastChannel`. Sem ele (navegadores antigos), o evento `storage`
// de uma chave neutra que guarda só um número aleatório — nunca dado de sessão.
export const SESSION_CHANNEL_NAME = 'mplacas-session'
export const SESSION_SIGNAL_STORAGE_KEY = 'mplacas:account-switch'

let channel: BroadcastChannel | null | undefined

// Uma única instância por aba, para enviar e receber: o `BroadcastChannel` não
// entrega a mensagem ao próprio objeto que a enviou, então a aba que fez o
// login não reage ao próprio aviso.
function sessionChannel(): BroadcastChannel | null {
  if (channel === undefined) {
    channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel(SESSION_CHANNEL_NAME) : null
  }
  return channel
}

export function announceSessionChange(): void {
  const ch = sessionChannel()
  if (ch) {
    ch.postMessage({ type: 'changed' })
    return
  }
  safeStorage.set(SESSION_SIGNAL_STORAGE_KEY, String(Math.random()))
}

export function subscribeSessionChanges(onChange: () => void): () => void {
  const ch = sessionChannel()
  if (ch) {
    const listener = (event: MessageEvent) => {
      if ((event.data as { type?: unknown } | null)?.type === 'changed') onChange()
    }
    ch.addEventListener('message', listener)
    return () => ch.removeEventListener('message', listener)
  }
  if (typeof window === 'undefined') return () => undefined
  const listener = (event: StorageEvent) => {
    if (event.key === SESSION_SIGNAL_STORAGE_KEY) onChange()
  }
  window.addEventListener('storage', listener)
  return () => window.removeEventListener('storage', listener)
}

// Duas abas pedindo refresh juntas: o backend tolera a perdedora por 10 s
// respondendo 401 sem apagar o cookie (ADR-102 § 4). Repetimos uma vez, depois
// de dar tempo à resposta da vencedora gravar o cookie novo.
export const REFRESH_RETRY_DELAY_MS = 300

async function refreshOnce(epoch: number): Promise<RefreshOutcome | 401> {
  if (epoch !== sessionEpoch) return { kind: 'superseded' }
  let response: Response
  try {
    // Sem corpo: a credencial é o cookie.
    response = await authFetch('/auth/refresh', { method: 'POST' })
  } catch {
    return { kind: 'unreachable' }
  }
  if (epoch !== sessionEpoch) return { kind: 'superseded' }
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
  // Conferida de novo logo antes de gravar (o corpo pode ter demorado).
  if (epoch !== sessionEpoch) return { kind: 'superseded' }
  TokenStore.set(accessToken)
  return { kind: 'ok', accessToken }
}

async function refreshWithRetry(epoch: number): Promise<RefreshOutcome> {
  const first = await refreshOnce(epoch)
  if (first !== 401) return first
  await new Promise((resolve) => setTimeout(resolve, REFRESH_RETRY_DELAY_MS))
  const second = await refreshOnce(epoch)
  return second === 401 ? { kind: 'unauthenticated' } : second
}

// Serializa entre abas com a Web Locks API: a segunda aba só pede o refresh
// depois que a primeira recebeu a resposta (e o navegador gravou o cookie
// rotacionado). Sem suporte, vale só o single-flight dentro da aba.
export const REFRESH_LOCK_NAME = 'mplacas-refresh'

function webLocks(): LockManager | undefined {
  const locks = typeof navigator === 'undefined' ? undefined : navigator.locks
  return locks && typeof locks.request === 'function' ? locks : undefined
}

function withRefreshLock<T>(task: () => Promise<T>): Promise<T> {
  const locks = webLocks()
  if (!locks) return task()
  return locks.request(REFRESH_LOCK_NAME, task) as Promise<T>
}

// Single-flight dentro da aba (A-02): requisições concorrentes compartilham a
// mesma renovação. O `finally` limpa a referência mesmo em falha.
let refreshInFlight: Promise<RefreshOutcome> | null = null

export function refreshSession(): Promise<RefreshOutcome> {
  if (refreshInFlight === null) {
    const epoch = sessionEpoch
    refreshInFlight = withRefreshLock(() => refreshWithRetry(epoch))
      .catch((): RefreshOutcome => ({ kind: 'unreachable' }))
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

// Abre sessão (login, aceite de convite) depois de qualquer refresh em voo e
// atrás do mesmo lock: o `Set-Cookie` de quem entra é sempre o último a chegar,
// e nenhum refresh atrasado da sessão anterior o sobrescreve. A `task` grava a
// sessão (`markSessionChanged` + `TokenStore.set`) ainda dentro do lock.
export async function openSession<T>(task: () => Promise<T>): Promise<T> {
  if (refreshInFlight !== null) await refreshInFlight.catch(() => undefined)
  return withRefreshLock(task)
}

// Quanto o logout espera pelo lock (um refresh de outra aba pode estar
// segurando-o por até um minuto com o Render acordando). Depois disso o pedido
// sai mesmo assim: sair não pode ficar preso.
export const LOGOUT_LOCK_WAIT_MS = 3_000

function sendLogout(): Promise<Response> {
  return fetch(`${API_URL}/auth/logout`, authRequestInit({ method: 'POST', keepalive: true }))
}

function timeoutSignal(ms: number): AbortSignal {
  if (typeof AbortSignal.timeout === 'function') return AbortSignal.timeout(ms)
  const controller = new AbortController()
  setTimeout(() => controller.abort(), ms)
  return controller.signal
}

function isLockWaitAbort(error: unknown): boolean {
  const name = (error as { name?: unknown } | null)?.name
  return name === 'AbortError' || name === 'TimeoutError'
}

// Encerra a sessão no servidor: revoga e apaga o cookie. Melhor esforço — falha
// de rede não restaura nada localmente e não é repetida. `keepalive` deixa o
// pedido terminar mesmo se a aba fechar logo em seguida.
//
// Passa pelo lock do refresh, esperando no máximo `LOGOUT_LOCK_WAIT_MS`. Se a
// espera estourar (outra aba segurando o lock com o Render acordando), envia
// sem o lock e, em segundo plano, manda um segundo logout quando o lock vagar:
// o refresh que estava em voo pode ter gravado um cookie novo, que sobraria.
// O segundo só sai se a sessão desta aba não mudou de novo nesse meio-tempo
// (um login logo depois passaria pelo mesmo lock, depois deste pedido).
export async function revokeSession(): Promise<void> {
  const epoch = sessionEpoch
  const secondLogout = () => (epoch === sessionEpoch ? sendLogout() : Promise.resolve(undefined))
  try {
    const locks = webLocks()
    if (!locks) {
      const inFlight = refreshInFlight
      if (inFlight === null) {
        await sendLogout()
        return
      }
      const settled = await Promise.race([
        inFlight.then(() => true, () => true),
        new Promise<boolean>((resolve) => setTimeout(() => resolve(false), LOGOUT_LOCK_WAIT_MS)),
      ])
      await sendLogout()
      if (!settled) void inFlight.then(secondLogout, secondLogout).catch(() => undefined)
      return
    }
    try {
      await locks.request(REFRESH_LOCK_NAME, { signal: timeoutSignal(LOGOUT_LOCK_WAIT_MS) }, sendLogout)
    } catch (error) {
      // Só a espera pelo lock estourou: envia sem o lock. Erro do próprio envio
      // (rede) cai no `catch` de fora e não é repetido.
      if (!isLockWaitAbort(error)) return
      await sendLogout()
      void Promise.resolve(locks.request(REFRESH_LOCK_NAME, secondLogout)).catch(() => undefined)
    }
  } catch {
    // melhor esforço
  }
}
