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
  const request = vi.fn((name: string, optionsOrTask: unknown, maybeTask?: () => Promise<unknown>) => {
    const task = (typeof optionsOrTask === 'function' ? optionsOrTask : maybeTask) as () => Promise<unknown>
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

// Web Locks com "dono externo": outra aba segura o lock até `release()`.
// Respeita `options.signal` como o navegador (rejeita com o motivo do abort se
// o lock não foi concedido a tempo).
function installHeldLocks() {
  let release: () => void = () => undefined
  let held: Promise<void> = new Promise<void>((resolve) => { release = resolve })
  const request = vi.fn((name: string, optionsOrTask: unknown, maybeTask?: () => Promise<unknown>) => {
    const task = (typeof optionsOrTask === 'function' ? optionsOrTask : maybeTask) as () => Promise<unknown>
    const signal = typeof optionsOrTask === 'function' ? undefined : (optionsOrTask as { signal?: AbortSignal }).signal
    void name
    return new Promise((resolve, reject) => {
      let granted = false
      signal?.addEventListener('abort', () => {
        if (!granted) reject(signal.reason ?? new DOMException('aborted', 'AbortError'))
      })
      const mine = held.then(async () => {
        if (signal?.aborted) return
        granted = true
        try {
          resolve(await task())
        } catch (error) {
          reject(error)
        }
      })
      held = mine.then(() => undefined)
    })
  })
  vi.stubGlobal('navigator', { ...navigator, locks: { request } })
  return { request, release: () => release() }
}

describe('revokeSession — lock ocupado por outra aba (revisão do 8eb5128)', () => {
  it('lock ocupado: o logout sai em ~3 s sem o lock e, quando o lock vaga, sai um segundo logout', async () => {
    const locks = installHeldLocks()
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const started = Date.now()

    await revokeSession()

    const elapsed = Date.now() - started
    expect(elapsed).toBeGreaterThanOrEqual(2_900)
    expect(elapsed).toBeLessThan(5_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/api/auth/logout')

    // O refresh da outra aba termina e solta o lock: o cookie que sobrou é
    // revogado por um segundo logout.
    locks.release()
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe('/api/auth/logout')
  }, 10_000)

  it('erro de rede no logout não é repetido (nem pelo caminho do lock ocupado)', async () => {
    const locks = installHeldLocks()
    const fetchMock = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(revokeSession()).resolves.toBeUndefined()
    locks.release()
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(fetchMock).toHaveBeenCalledTimes(1)
  }, 10_000)

  it('erro de rede com o lock livre também sai uma vez só', async () => {
    installFakeLocks()
    const fetchMock = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })
    vi.stubGlobal('fetch', fetchMock)

    await revokeSession()
    await new Promise((resolve) => setTimeout(resolve, 20))

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('sem Web Locks: refresh em voo além de 3 s → logout já, e um segundo depois que o refresh termina', async () => {
    vi.stubGlobal('navigator', { ...navigator, locks: undefined })
    let answerRefresh: (response: Response) => void = () => undefined
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) =>
      String(input).endsWith('/auth/refresh')
        ? new Promise<Response>((resolve) => { answerRefresh = resolve })
        : Promise.resolve(new Response(null, { status: 204 })),
    )
    vi.stubGlobal('fetch', fetchMock)
    const logouts = () => fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/auth/logout')).length

    const refreshing = refreshSession()
    await revokeSession()
    expect(logouts()).toBe(1)

    answerRefresh(json({ access_token: 'qualquer' }))
    await refreshing
    await vi.waitFor(() => expect(logouts()).toBe(2))
  }, 10_000)
})

describe('aviso de troca de sessão entre abas (BroadcastChannel)', () => {
  it('duas abas (dois módulos): o aviso de uma chega à outra, e não à própria', async () => {
    vi.resetModules()
    const tabA = await import('./session')
    vi.resetModules()
    const tabB = await import('./session')
    const onA = vi.fn()
    const onB = vi.fn()
    const offA = tabA.subscribeSessionChanges(onA)
    const offB = tabB.subscribeSessionChanges(onB)

    tabA.announceSessionChange()

    await vi.waitFor(() => expect(onB).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(onA).not.toHaveBeenCalled()
    offA()
    offB()
  })

  it('mensagem que não é o aviso esperado é ignorada', async () => {
    vi.resetModules()
    const tab = await import('./session')
    const onChange = vi.fn()
    const off = tab.subscribeSessionChanges(onChange)
    const other = new BroadcastChannel(tab.SESSION_CHANNEL_NAME)

    other.postMessage({ type: 'outra-coisa', token: 'x' })
    await new Promise((resolve) => setTimeout(resolve, 30))

    expect(onChange).not.toHaveBeenCalled()
    other.close()
    off()
  })

  it('sem BroadcastChannel: usa o evento storage de uma chave neutra, só com um número', async () => {
    vi.stubGlobal('BroadcastChannel', undefined)
    vi.resetModules()
    const tab = await import('./session')
    const onChange = vi.fn()
    const off = tab.subscribeSessionChanges(onChange)

    tab.announceSessionChange()
    const stored = window.localStorage.getItem(tab.SESSION_SIGNAL_STORAGE_KEY)
    expect(stored).toMatch(/^0\.\d+$/)

    // O navegador entrega o `storage` às OUTRAS abas; aqui simulamos a outra.
    window.dispatchEvent(new StorageEvent('storage', { key: tab.SESSION_SIGNAL_STORAGE_KEY, newValue: stored }))
    window.dispatchEvent(new StorageEvent('storage', { key: 'mplacas:theme', newValue: 'dark' }))

    expect(onChange).toHaveBeenCalledTimes(1)
    off()
    window.localStorage.removeItem(tab.SESSION_SIGNAL_STORAGE_KEY)
  })
})
