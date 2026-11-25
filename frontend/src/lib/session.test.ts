import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { REFRESH_LOCK_NAME, refreshSession, revokeSession } from './session'
import { TokenStore } from './auth'

// Transporte da sessão (ADR-102): refresh pelo cookie HttpOnly, serializado
// entre abas pela Web Locks API, com uma repetição em 401.

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

// Web Locks mínimo e fiel ao que importa: pedidos com o mesmo nome rodam um de
// cada vez, na ordem de chegada — como duas abas do mesmo navegador.
function installFakeLocks() {
  const names: string[] = []
  let tail: Promise<unknown> = Promise.resolve()
  const request = vi.fn((name: string, task: () => Promise<unknown>) => {
    names.push(name)
    const run = tail.then(() => task())
    tail = run.catch(() => undefined)
    return run
  })
  vi.stubGlobal('navigator', { ...navigator, locks: { request } })
  return { request, names }
}

beforeEach(() => {
  TokenStore.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  TokenStore.clear()
})

describe('refreshSession', () => {
  it('pede pelo cookie: POST sem corpo, credentials same-origin e X-Mplacas-Auth', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => json({ access_token: 'novo' }))
    vi.stubGlobal('fetch', fetchMock)

    const outcome = await refreshSession()

    expect(outcome).toEqual({ kind: 'ok', accessToken: 'novo' })
    expect(TokenStore.get()).toBe('novo')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/auth/refresh')
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
    expect(init.credentials).toBe('same-origin')
    expect(init.referrerPolicy).toBe('same-origin')
    expect(new Headers(init.headers).get('X-Mplacas-Auth')).toBe('1')
  })

  it('ignora um refresh_token no corpo: nada além do access token fica em memória', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ access_token: 'acesso', refresh_token: 'NAO-GUARDAR' })))

    const outcome = await refreshSession()

    expect(JSON.stringify(outcome)).not.toContain('NAO-GUARDAR')
    expect(TokenStore.get()).toBe('acesso')
  })

  it('duas abas (dois módulos, um só navegador) renovam uma de cada vez pelo lock "mplacas-refresh"', async () => {
    const locks = installFakeLocks()
    // Cada aba tem seu próprio módulo (e single-flight); o lock é do navegador.
    vi.resetModules()
    const tabA = await import('./session')
    vi.resetModules()
    const tabB = await import('./session')
    expect(tabA.refreshSession).not.toBe(tabB.refreshSession)

    let active = 0
    let maxActive = 0
    let n = 0
    vi.stubGlobal('fetch', vi.fn(async () => {
      active += 1
      maxActive = Math.max(maxActive, active)
      await new Promise((resolve) => setTimeout(resolve, 5))
      active -= 1
      n += 1
      return json({ access_token: `t${n}` })
    }))

    const [a, b] = await Promise.all([tabA.refreshSession(), tabB.refreshSession()])

    expect(locks.names).toEqual([REFRESH_LOCK_NAME, REFRESH_LOCK_NAME])
    expect(maxActive).toBe(1)
    expect([a, b]).toEqual([
      { kind: 'ok', accessToken: 't1' },
      { kind: 'ok', accessToken: 't2' },
    ])
  })

  it('chamadas concorrentes na mesma aba compartilham uma renovação (single-flight)', async () => {
    installFakeLocks()
    const fetchMock = vi.fn(async () => json({ access_token: 'x' }))
    vi.stubGlobal('fetch', fetchMock)

    await Promise.all([refreshSession(), refreshSession(), refreshSession()])

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('sem Web Locks, continua funcionando com o single-flight da aba', async () => {
    vi.stubGlobal('navigator', { ...navigator, locks: undefined })
    const fetchMock = vi.fn(async () => json({ access_token: 'y' }))
    vi.stubGlobal('fetch', fetchMock)

    await Promise.all([refreshSession(), refreshSession()])

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(TokenStore.get()).toBe('y')
  })

  it('401 e depois 200 (outra aba acabou de rotacionar): repete uma vez e entra', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('', { status: 401 }))
      .mockResolvedValueOnce(json({ access_token: 'depois' }))
    vi.stubGlobal('fetch', fetchMock)

    expect(await refreshSession()).toEqual({ kind: 'ok', accessToken: 'depois' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('401 duas vezes: sem sessão, e não repete uma terceira', async () => {
    const fetchMock = vi.fn(async () => new Response('', { status: 401 }))
    vi.stubGlobal('fetch', fetchMock)

    expect(await refreshSession()).toEqual({ kind: 'unauthenticated' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it.each([
    ['falha de rede', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['504 do proxy', () => Promise.resolve(new Response('', { status: 504 }))],
    ['503 sem configuração', () => Promise.resolve(new Response('', { status: 503 }))],
  ])('%s: inalcançável (não manda ao login)', async (_nome, respond) => {
    vi.stubGlobal('fetch', vi.fn(respond))
    expect(await refreshSession()).toEqual({ kind: 'unreachable' })
    expect(TokenStore.get()).toBeNull()
  })

  it('403 (origem recusada) conta como sem sessão', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'request origin not allowed' }, 403)))
    expect(await refreshSession()).toEqual({ kind: 'unauthenticated' })
  })
})

describe('revokeSession (logout)', () => {
  it('POST /api/auth/logout com keepalive, credentials same-origin, cabeçalho e sem corpo', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await revokeSession()

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/auth/logout')
    expect(init.method).toBe('POST')
    expect(init.keepalive).toBe(true)
    expect(init.credentials).toBe('same-origin')
    expect(init.body).toBeUndefined()
    expect(new Headers(init.headers).get('X-Mplacas-Auth')).toBe('1')
  })

  it('falha de rede no logout não lança', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }))
    await expect(revokeSession()).resolves.toBeUndefined()
  })
})
