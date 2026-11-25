// @vitest-environment node
// Proxy `/api/*` da Pages Function (ADR-102). `fetch` do backend é simulado:
// nenhum teste sai para a rede, e nenhum segredo real é usado.
import { describe, expect, it, vi } from 'vitest'
import { proxyApiRequest, type ProxyEnv } from './apiProxy'

const ORIGIN = 'https://mplacas-api.example.test'
const SECRET = 'segredo-de-teste-com-mais-de-32-bytes-0123456789'
const ENV: ProxyEnv = { MPLACAS_API_ORIGIN: ORIGIN, MPLACAS_PROXY_SHARED_SECRET: SECRET }

function upstreamOk(body: BodyInit | null = '{"ok":true}', init: ResponseInit = {}) {
  return vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' }, ...init }),
  )
}

function call(fetchMock: ReturnType<typeof upstreamOk>) {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  return { url, init, headers: new Headers(init.headers) }
}

describe('proxyApiRequest — destino', () => {
  it('tira /api e repassa método, caminho, consulta e corpo à origem configurada', async () => {
    const fetchMock = upstreamOk()
    const request = new Request('https://mplacas-frontend.pages.dev/api/plants/1/location?x=1&y=2', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ latitude: '1' }),
    })

    const response = await proxyApiRequest(request, ENV, fetchMock)

    expect(response.status).toBe(200)
    const { url, init } = call(fetchMock)
    expect(url).toBe(`${ORIGIN}/plants/1/location?x=1&y=2`)
    expect(init.method).toBe('PATCH')
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe('{"latitude":"1"}')
    expect(init.redirect).toBe('manual')
  })

  it('caminho "//outro-host" não troca o host do destino', async () => {
    const fetchMock = upstreamOk()
    await proxyApiRequest(new Request('https://site.test/api//evil.example/x'), ENV, fetchMock)
    expect(new URL(call(fetchMock).url).origin).toBe(ORIGIN)
  })

  it('GET não leva corpo', async () => {
    const fetchMock = upstreamOk()
    await proxyApiRequest(new Request('https://site.test/api/health'), ENV, fetchMock)
    expect(call(fetchMock).init.body).toBeUndefined()
  })
})

describe('proxyApiRequest — cabeçalhos do pedido', () => {
  it('repassa só a lista permitida e descarta hop-by-hop e cabeçalhos de confiança forjados', async () => {
    const fetchMock = upstreamOk()
    const request = new Request('https://site.test/api/auth/refresh', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        Authorization: 'Bearer abc',
        Cookie: '__Secure-mplacas_rt=valor-de-teste',
        Origin: 'https://mplacas-frontend.pages.dev',
        'X-Mplacas-Auth': '1',
        'X-Request-Id': 'req-1',
        'Content-Type': 'application/json',
        // Forjados pelo cliente — nunca podem chegar ao backend:
        'X-Mplacas-Client-IP': '6.6.6.6',
        'X-Mplacas-Proxy-Secret': 'chute',
        'X-Forwarded-For': '1.2.3.4',
        'X-Forwarded-Host': 'evil.example',
        'X-Forwarded-Proto': 'http',
        // Hop-by-hop / irrelevantes:
        Connection: 'keep-alive, X-Custom',
        'Keep-Alive': 'timeout=5',
        'X-Custom': 'x',
        Referer: 'https://mplacas-frontend.pages.dev/dashboard?segredo=1',
        'CF-Connecting-IP': '203.0.113.7',
      },
    })

    await proxyApiRequest(request, ENV, fetchMock)

    const { headers } = call(fetchMock)
    expect(headers.get('accept')).toBe('application/json')
    expect(headers.get('authorization')).toBe('Bearer abc')
    expect(headers.get('cookie')).toBe('__Secure-mplacas_rt=valor-de-teste')
    expect(headers.get('origin')).toBe('https://mplacas-frontend.pages.dev')
    expect(headers.get('x-mplacas-auth')).toBe('1')
    expect(headers.get('x-request-id')).toBe('req-1')
    expect(headers.get('content-type')).toBe('application/json')

    expect(headers.get('x-mplacas-client-ip')).toBe('203.0.113.7')
    expect(headers.get('x-mplacas-proxy-secret')).toBe(SECRET)
    for (const name of ['x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto', 'connection', 'keep-alive', 'x-custom', 'referer', 'cf-connecting-ip', 'host']) {
      expect(headers.has(name), name).toBe(false)
    }
  })

  it('sem CF-Connecting-IP não inventa IP, mesmo com X-Mplacas-Client-IP do cliente', async () => {
    const fetchMock = upstreamOk()
    await proxyApiRequest(
      new Request('https://site.test/api/auth/login', { method: 'POST', headers: { 'X-Mplacas-Client-IP': '6.6.6.6' }, body: '{}' }),
      ENV,
      fetchMock,
    )
    const { headers } = call(fetchMock)
    expect(headers.has('x-mplacas-client-ip')).toBe(false)
    expect(headers.get('x-mplacas-proxy-secret')).toBe(SECRET)
  })
})

describe('proxyApiRequest — resposta', () => {
  it('preserva status, corpo e VÁRIOS Set-Cookie separados', async () => {
    const upstreamHeaders = new Headers({ 'Content-Type': 'application/json', 'X-Request-Id': 'r-9' })
    upstreamHeaders.append('Set-Cookie', '__Secure-mplacas_rt=novo; HttpOnly; Secure; SameSite=Strict; Path=/api/auth; Max-Age=100')
    upstreamHeaders.append('Set-Cookie', 'outro=1; Expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/api/auth')
    const fetchMock = vi.fn(async () => new Response('{"access_token":"a"}', { status: 200, headers: upstreamHeaders }))

    const response = await proxyApiRequest(new Request('https://site.test/api/auth/refresh', { method: 'POST' }), ENV, fetchMock)

    expect(response.status).toBe(200)
    expect(await response.text()).toBe('{"access_token":"a"}')
    expect(response.headers.get('x-request-id')).toBe('r-9')
    expect(response.headers.getSetCookie()).toEqual([
      '__Secure-mplacas_rt=novo; HttpOnly; Secure; SameSite=Strict; Path=/api/auth; Max-Age=100',
      'outro=1; Expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/api/auth',
    ])
  })

  it('não vaza cabeçalhos de infraestrutura do backend', async () => {
    const fetchMock = vi.fn(async () =>
      new Response('{}', {
        status: 401,
        headers: {
          Server: 'uvicorn',
          Via: '1.1 render',
          'X-Powered-By': 'x',
          'X-Render-Origin-Server': 'interno',
          'Rndr-Id': 'abc',
          'CF-Ray': 'xyz',
          'Content-Type': 'application/json',
        },
      }),
    )

    const response = await proxyApiRequest(new Request('https://site.test/api/auth/refresh', { method: 'POST' }), ENV, fetchMock)

    expect(response.status).toBe(401)
    for (const name of ['server', 'via', 'x-powered-by', 'x-render-origin-server', 'rndr-id', 'cf-ray']) {
      expect(response.headers.has(name), name).toBe(false)
    }
    expect(response.headers.get('content-type')).toBe('application/json')
  })

  it('204 sai sem corpo', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }))
    const response = await proxyApiRequest(new Request('https://site.test/api/auth/logout', { method: 'POST' }), ENV, fetchMock)
    expect(response.status).toBe(204)
    expect(response.body).toBeNull()
  })

  it('Location do próprio backend é reescrito para /api, sem revelar o host', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 307, headers: { Location: `${ORIGIN}/plants/?x=1` } }))
    const response = await proxyApiRequest(new Request('https://site.test/api/plants?x=1'), ENV, fetchMock)
    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('/api/plants/?x=1')
  })

  it('corpo em fluxo passa adiante', async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('parte-1,'))
        controller.enqueue(new TextEncoder().encode('parte-2'))
        controller.close()
      },
    })
    const fetchMock = vi.fn(async () => new Response(stream, { status: 200, headers: { 'Content-Type': 'text/csv' } }))
    const response = await proxyApiRequest(new Request('https://site.test/api/reports/monthly/latest.csv'), ENV, fetchMock)
    expect(await response.text()).toBe('parte-1,parte-2')
  })
})

describe('proxyApiRequest — falha fechada', () => {
  it.each([
    ['origem ausente', { MPLACAS_PROXY_SHARED_SECRET: SECRET }],
    ['origem http', { MPLACAS_API_ORIGIN: 'http://mplacas-api.example.test', MPLACAS_PROXY_SHARED_SECRET: SECRET }],
    ['origem com caminho', { MPLACAS_API_ORIGIN: `${ORIGIN}/v1`, MPLACAS_PROXY_SHARED_SECRET: SECRET }],
    ['origem inválida', { MPLACAS_API_ORIGIN: 'não é url', MPLACAS_PROXY_SHARED_SECRET: SECRET }],
    ['segredo ausente', { MPLACAS_API_ORIGIN: ORIGIN }],
    ['segredo em branco', { MPLACAS_API_ORIGIN: ORIGIN, MPLACAS_PROXY_SHARED_SECRET: '   ' }],
    ['segredo curto', { MPLACAS_API_ORIGIN: ORIGIN, MPLACAS_PROXY_SHARED_SECRET: 'curto' }],
  ])('%s → 503 genérico, sem chamar o backend', async (_nome, env) => {
    const fetchMock = upstreamOk()

    const response = await proxyApiRequest(new Request('https://site.test/api/health'), env as ProxyEnv, fetchMock)

    expect(response.status).toBe(503)
    expect(await response.json()).toEqual({ detail: 'service unavailable' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('origem configurada igual ao próprio site → 503 (evita laço)', async () => {
    const fetchMock = upstreamOk()
    const response = await proxyApiRequest(
      new Request(`${ORIGIN}/api/health`),
      ENV,
      fetchMock,
    )
    expect(response.status).toBe(503)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('backend que não responde (Render acordando) → 504 genérico no prazo', async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      }),
    )

    const response = await proxyApiRequest(new Request('https://site.test/api/auth/refresh', { method: 'POST' }), ENV, fetchMock, 20)

    expect(response.status).toBe(504)
    expect(await response.json()).toEqual({ detail: 'upstream timeout' })
  })

  it('falha de conexão → 502 genérico, sem detalhe do erro', async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError('connect ECONNREFUSED 10.0.0.5:10000')
    })
    const response = await proxyApiRequest(new Request('https://site.test/api/health'), ENV, fetchMock)
    expect(response.status).toBe(502)
    expect(await response.text()).not.toContain('10.0.0.5')
  })

  it('corpo declarado grande demais → 413 sem chamar o backend', async () => {
    const fetchMock = upstreamOk()
    const response = await proxyApiRequest(
      new Request('https://site.test/api/billing/intake-pdf', {
        method: 'POST',
        headers: { 'Content-Length': String(26 * 1024 * 1024) },
        body: 'x',
      }),
      ENV,
      fetchMock,
    )
    expect(response.status).toBe(413)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('não escreve nada no console (nem segredo, nem cookie, nem corpo)', async () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m))
    const fetchMock = vi.fn(async () => {
      throw new Error('falha')
    })
    await proxyApiRequest(
      new Request('https://site.test/api/auth/login', { method: 'POST', headers: { Cookie: 'a=b' }, body: '{"password":"x"}' }),
      ENV,
      fetchMock,
    )
    for (const spy of spies) expect(spy).not.toHaveBeenCalled()
    vi.restoreAllMocks()
  })
})
