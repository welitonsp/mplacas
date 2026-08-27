import { describe, expect, it, vi, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useAuth, AuthProvider } from './AuthContext'
import { TokenStore } from '../lib/auth'
import { SELECTED_PLANT_STORAGE_KEY } from './PlantContext'

vi.mock('../env', () => ({
  API_URL: 'https://api.example.test',
}))

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
