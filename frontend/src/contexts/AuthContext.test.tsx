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
