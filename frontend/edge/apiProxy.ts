// Proxy first-party `/api/*` → API no Render (ADR-102, etapa 2).
//
// Roda como Cloudflare Pages Function (`functions/api/[[path]].ts` só delega
// para cá; a lógica mora fora de `functions/` porque todo arquivo lá vira rota,
// inclusive um `.test.ts`). Para o navegador a API passa a ser a própria origem
// do site: o cookie `__Secure-mplacas_rt` (`SameSite=Strict`, `Path=/api/auth`)
// viaja, e a CSP fica em `connect-src 'self'`.
//
// Regras:
// - configuração ausente ou inválida → 503 genérico, nunca um repasse "meio
//   configurado" (falha fechada);
// - só cabeçalhos de uma lista permitida vão ao backend; os que o backend usa
//   para confiar no IP do cliente (`X-Mplacas-Client-IP`,
//   `X-Mplacas-Proxy-Secret`) e qualquer `X-Forwarded-*` vindos do navegador são
//   descartados e só este código os escreve;
// - nada de log: nem cabeçalho, nem cookie, nem corpo, nem segredo;
// - backend lento (Render acordando) → 504 genérico antes do prazo do cliente.

export interface ProxyEnv {
  // Origem exata da API, ex.: https://mplacas-api.onrender.com (sem caminho).
  MPLACAS_API_ORIGIN?: string
  // Mesmo valor de `MPLACAS_PROXY_SHARED_SECRET` no Render; mínimo 32 bytes.
  MPLACAS_PROXY_SHARED_SECRET?: string
}

export const API_PREFIX = '/api'
export const MIN_SHARED_SECRET_BYTES = 32
// O cliente desiste em 60 s (`AUTH_TIMEOUT_MS`/`DATA_TIMEOUT_MS`); o proxy corta
// antes para devolver uma resposta clara (504) em vez de deixar o cliente abortar.
export const UPSTREAM_TIMEOUT_MS = 58_000
// Corpo de pedido acima disto nem é lido (o maior uso real é o PDF da fatura,
// limitado bem abaixo no backend).
export const MAX_REQUEST_BODY_BYTES = 25 * 1024 * 1024

// Cabeçalhos do navegador que o backend precisa. Todo o resto fica para trás:
// hop-by-hop, `Host`, `X-Forwarded-*`, `CF-*`, `Referer`, `User-Agent` etc.
export const FORWARDED_REQUEST_HEADERS: readonly string[] = [
  'accept',
  'accept-language',
  'authorization',
  'content-type',
  'cookie',
  'if-match',
  'if-modified-since',
  'if-none-match',
  // O backend confere o `Origin` em login, aceite de convite, refresh e logout.
  'origin',
  // Rastreamento W3C (correlação de logs ponta a ponta); não carrega segredo.
  'traceparent',
  'x-mplacas-auth',
  'x-request-id',
  // Fora de propósito: `x-api-key`. A chave de API é para integração
  // servidor-a-servidor, que chama o Render direto — nunca pelo navegador.
]

// Cabeçalhos de resposta que não voltam ao navegador: hop-by-hop, os que o
// runtime recalcula e os que só revelam a infraestrutura do backend.
const DROPPED_RESPONSE_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'content-length',
  'server',
  'via',
  'x-powered-by',
  'alt-svc',
  'nel',
  'report-to',
])
const DROPPED_RESPONSE_PREFIXES = ['x-render-', 'rndr-', 'cf-']

const JSON_HEADERS = { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }

function genericError(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), { status, headers: JSON_HEADERS })
}

// Origem configurada, validada: https, sem caminho/consulta/credenciais.
// `null` = configuração inválida → o proxy não roda.
export function parseApiOrigin(raw: string | undefined): string | null {
  if (typeof raw !== 'string' || raw.trim() === '') return null
  let url: URL
  try {
    url = new URL(raw.trim())
  } catch {
    return null
  }
  if (url.protocol !== 'https:') return null
  if (url.username || url.password || url.search || url.hash) return null
  if (url.pathname !== '/' && url.pathname !== '') return null
  return url.origin
}

function byteLength(value: string): number {
  return new TextEncoder().encode(value).length
}

export function hasUsableSecret(secret: string | undefined): secret is string {
  return typeof secret === 'string' && secret.trim() !== '' && byteLength(secret) >= MIN_SHARED_SECRET_BYTES
}

export function buildUpstreamHeaders(request: Request, secret: string): Headers {
  const headers = new Headers()
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name)
    if (value !== null) headers.set(name, value)
  }
  // IP do cliente como a borda da Cloudflare o viu — o navegador não consegue
  // forjar `CF-Connecting-IP`. Só vale no backend com o segredo junto.
  const clientIp = request.headers.get('cf-connecting-ip')
  if (clientIp) headers.set('X-Mplacas-Client-IP', clientIp)
  headers.set('X-Mplacas-Proxy-Secret', secret)
  return headers
}

// `Location` apontando para o próprio backend (ex.: redirecionamento de barra
// final) é reescrito para `/api/...`; o navegador nunca vê o host do Render.
function rewriteLocation(location: string, apiOrigin: string): string {
  try {
    const target = new URL(location, apiOrigin)
    if (target.origin !== apiOrigin) return location
    return `${API_PREFIX}${target.pathname}${target.search}${target.hash}`
  } catch {
    return location
  }
}

export function buildClientResponse(upstream: Response, apiOrigin: string): Response {
  const headers = new Headers()
  upstream.headers.forEach((value, name) => {
    const key = name.toLowerCase()
    if (key === 'set-cookie') return // tratado abaixo, um por um
    if (DROPPED_RESPONSE_HEADERS.has(key)) return
    if (DROPPED_RESPONSE_PREFIXES.some((prefix) => key.startsWith(prefix))) return
    headers.set(name, key === 'location' ? rewriteLocation(value, apiOrigin) : value)
  })
  // Vários `Set-Cookie` não podem ser fundidos numa linha com vírgula (a data
  // do `Expires` tem vírgula); `getSetCookie()` devolve cada um separado.
  for (const cookie of upstream.headers.getSetCookie()) headers.append('Set-Cookie', cookie)

  const nullBody = upstream.status === 204 || upstream.status === 205 || upstream.status === 304
  return new Response(nullBody ? null : upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  })
}

// Lê o corpo até `maxBytes`; `null` se passar disso (a leitura é cancelada).
export async function readBodyLimited(request: Request, maxBytes: number): Promise<ArrayBuffer | undefined | null> {
  if (request.body === null) return undefined
  const reader = request.body.getReader()
  const chunks: Uint8Array[] = []
  let total = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    total += value.byteLength
    if (total > maxBytes) {
      await reader.cancel().catch(() => undefined)
      return null
    }
    chunks.push(value)
  }
  const merged = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    merged.set(chunk, offset)
    offset += chunk.byteLength
  }
  return merged.buffer
}

export async function proxyApiRequest(
  request: Request,
  env: ProxyEnv,
  fetchImpl: typeof fetch = fetch,
  timeoutMs: number = UPSTREAM_TIMEOUT_MS,
): Promise<Response> {
  const apiOrigin = parseApiOrigin(env.MPLACAS_API_ORIGIN)
  const secret = env.MPLACAS_PROXY_SHARED_SECRET
  // Sem o segredo, o backend não confia no IP do cliente e todos os pedidos
  // chegariam com o IP da Cloudflare: o bloqueio de tentativas de login viraria
  // "por usuário", e qualquer um bloquearia o login de outro errando a senha
  // dele 5 vezes (ADR-102 § 6). Melhor não servir a API do que servir assim.
  if (apiOrigin === null || !hasUsableSecret(secret)) {
    return genericError(503, 'service unavailable')
  }

  const incoming = new URL(request.url)
  // Nunca repassar para a própria origem (laço infinito por erro de configuração).
  if (incoming.origin === apiOrigin) return genericError(503, 'service unavailable')
  if (incoming.pathname !== API_PREFIX && !incoming.pathname.startsWith(`${API_PREFIX}/`)) {
    return genericError(404, 'not found')
  }

  // Concatenação, não `new URL(path, origin)`: um caminho `//outro-host/...`
  // trocaria o host. Conferido de novo depois, por garantia.
  const path = incoming.pathname.slice(API_PREFIX.length) || '/'
  const target = new URL(`${apiOrigin}${path}${incoming.search}`)
  if (target.origin !== apiOrigin) return genericError(400, 'bad request')

  const method = request.method.toUpperCase()
  let body: ArrayBuffer | undefined
  if (method !== 'GET' && method !== 'HEAD') {
    const declared = Number(request.headers.get('content-length') ?? '0')
    if (Number.isFinite(declared) && declared > MAX_REQUEST_BODY_BYTES) {
      return genericError(413, 'request too large')
    }
    // Corpo lido inteiro: o backend recebe `Content-Length` real (os limites de
    // upload dele dependem disso). Lido em pedaços com teto, para um corpo sem
    // `Content-Length` (chunked) não encher a memória do Worker antes do 413.
    const limited = await readBodyLimited(request, MAX_REQUEST_BODY_BYTES)
    if (limited === null) return genericError(413, 'request too large')
    body = limited
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const upstream = await fetchImpl(target.toString(), {
      method,
      headers: buildUpstreamHeaders(request, secret),
      body,
      redirect: 'manual',
      signal: controller.signal,
    })
    return buildClientResponse(upstream, apiOrigin)
  } catch {
    // Sem detalhe do erro: pode conter host/endereço interno do backend.
    if (controller.signal.aborted) return genericError(504, 'upstream timeout')
    return genericError(502, 'upstream unavailable')
  } finally {
    clearTimeout(timer)
  }
}
