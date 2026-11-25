import { describe, expect, it, vi, beforeEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useAuth, AuthProvider } from './AuthContext'
import { TokenStore } from '../lib/auth'
import { SELECTED_PLANT_STORAGE_KEY } from './PlantContext'

beforeEach(() => {
  TokenStore.clear()
  window.localStorage.clear()
  vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
})

describe('AuthContext — logout limpa a usina selecionada (ADR-069, seção 5)', () => {
  it('remove mplacas_selected_plant_v1 do localStorage ao fazer logout', () => {
    window.localStorage.setItem(SELECTED_PLANT_STORAGE_KEY, 'some-plant-id')
    TokenStore.set('fake-token')

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    })

    act(() => {
      result.current.logout()
    })

    expect(window.localStorage.getItem(SELECTED_PLANT_STORAGE_KEY)).toBeNull()
  })

  it('não lança quando não havia usina selecionada previamente', () => {
    TokenStore.set('fake-token')

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    })

    expect(() => act(() => result.current.logout())).not.toThrow()
    expect(window.localStorage.getItem(SELECTED_PLANT_STORAGE_KEY)).toBeNull()
  })
})

describe('AuthContext — mensagem de login por status HTTP', () => {
  const renderAuth = () =>
    renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    })

  const loginWithStatus = async (status: number) => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status })))
    const { result } = renderAuth()
    let message = ''
    await act(async () => {
      try {
        await result.current.login('alguem', 'senha')
      } catch (err) {
        message = err instanceof Error ? err.message : String(err)
      }
    })
    return message
  }

  it('credencial errada culpa a credencial', async () => {
    expect(await loginWithStatus(401)).toBe('Credenciais inválidas.')
  })

  it('excesso de tentativas orienta a esperar', async () => {
    expect(await loginWithStatus(429)).toBe('Muitas tentativas. Aguarde e tente novamente.')
  })

  // Regressão do incidente de 2026-08-21: o banco recusou conexão por cota
  // esgotada, /auth/login passou a devolver 500, e a mensagem genérica mandava
  // o usuário "tentar novamente" uma ação que ficou impossível por dias — além
  // de sugerir que o problema era a senha dele.
  it.each([500, 502, 503, 504])(
    'status %i assume a falha como nossa e não manda repetir',
    async (status) => {
      const message = await loginWithStatus(status)

      expect(message).toContain('indisponível')
      expect(message).toContain('Não é a sua senha')
      // Não pode prometer que repetir resolve.
      expect(message).not.toContain('Tente novamente')
    },
  )
})

describe('AuthContext — falha antes de qualquer resposta HTTP', () => {
  const renderAuth = () =>
    renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    })

  const captureLoginError = async (run: (login: () => Promise<void>) => Promise<void>) => {
    const { result } = renderAuth()
    let message = ''
    await run(async () => {
      try {
        await result.current.login('alguem', 'senha')
      } catch (err) {
        message = err instanceof Error ? err.message : String(err)
      }
    })
    return message
  }

  it('sem conexão, aponta a conexão — e não diz que o servidor "demorou"', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }))

    const message = await captureLoginError(async (login) => {
      await act(login)
    })

    expect(message).toContain('Não foi possível conectar ao servidor')
    expect(message).not.toContain('demorou')
    expect(message).not.toContain('iniciando')
  })

  // Plano grátis do Render (ADR-076): a API hiberna e leva até ~60 s para
  // acordar. Prazo esgotado deve explicar isso, não culpar a rede do usuário.
  it('prazo esgotado explica que o servidor pode estar iniciando', async () => {
    vi.useFakeTimers()
    try {
      vi.stubGlobal('fetch', vi.fn((_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          )
        }),
      ))

      const message = await captureLoginError(async (login) => {
        await act(async () => {
          const pending = login()
          await vi.advanceTimersByTimeAsync(60_000)
          await pending
        })
      })

      expect(message).toContain('pode estar iniciando')
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('AuthContext — sessão pelo cookie (ADR-102)', () => {
  const renderAuth = () =>
    renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    })

  it('login guarda só o access token: o refresh_token do corpo nunca entra em memória', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      if (String(input).endsWith('/auth/login')) {
        return new Response(JSON.stringify({ access_token: 'acesso-1', refresh_token: 'REFRESH-SECRETO' }), { status: 200 })
      }
      return new Response(null, { status: 401 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderAuth()

    await act(async () => {
      await result.current.login('maria', 'senha')
    })

    expect(result.current.status).toBe('authenticated')
    expect(TokenStore.get()).toBe('acesso-1')
    // Nada exposto pelo contexto carrega o refresh token.
    expect(JSON.stringify(result.current)).not.toContain('REFRESH-SECRETO')

    const [, loginInit] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/auth/login')) as [string, RequestInit]
    expect(loginInit.credentials).toBe('same-origin')
    expect(new Headers(loginInit.headers).get('X-Mplacas-Auth')).toBe('1')

    // O logout depois do login também não leva o refresh token (só o cookie).
    act(() => result.current.logout())
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/auth/logout'))).toBe(true),
    )
    for (const [, init] of fetchMock.mock.calls) {
      expect(String(init?.body ?? '')).not.toContain('REFRESH-SECRETO')
    }
  })

  it('logout limpa a memória e chama /auth/logout com keepalive, credentials e o cabeçalho', async () => {
    TokenStore.set('acesso')
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderAuth()
    expect(result.current.status).toBe('authenticated')

    act(() => result.current.logout())

    expect(TokenStore.get()).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.sessionEnded).toBe(false)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/auth/logout')
    expect(init.keepalive).toBe(true)
    expect(init.credentials).toBe('same-origin')
    expect(init.body).toBeUndefined()
    expect(new Headers(init.headers).get('X-Mplacas-Auth')).toBe('1')
  })

  it('ao montar sem token, pergunta pelo cookie e adota o access token', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ access_token: 'do-cookie' }), { status: 200 })))
    const { result } = renderAuth()

    expect(result.current.status).toBe('checking')
    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    expect(TokenStore.get()).toBe('do-cookie')
    expect(result.current.sessionEnded).toBe(false)
  })

  it('um login feito enquanto a checagem roda não é desfeito pela resposta atrasada dela', async () => {
    let answerRefresh: (response: Response) => void = () => undefined
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith('/auth/refresh')) {
        return new Promise<Response>((resolve) => { answerRefresh = resolve })
      }
      return Promise.resolve(new Response(JSON.stringify({ access_token: 'do-login' }), { status: 200 }))
    }))
    const { result } = renderAuth()

    await act(async () => {
      await result.current.login('maria', 'senha')
    })
    await act(async () => {
      answerRefresh(new Response('', { status: 401 }))
      await new Promise((resolve) => setTimeout(resolve, 400))
    })

    expect(result.current.status).toBe('authenticated')
    expect(TokenStore.get()).toBe('do-login')
  })
})
