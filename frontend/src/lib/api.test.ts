import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_URL } from '../env'
import { fetchPlants } from './api'
import { TokenStore } from './auth'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('fetchPlants', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    TokenStore.clear()
  })

  it('chama GET /plants e devolve os itens já parseados', async () => {
    TokenStore.set('token-abc')
    const payload = {
      count: 2,
      items: [
        { id: '11111111-1111-1111-1111-111111111111', name: 'Matriz — Telhado A', installed_power_kwp: '48.600' },
        { id: '22222222-2222-2222-2222-222222222222', name: 'Filial Norte', installed_power_kwp: null },
      ],
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(payload))

    const plants = await fetchPlants()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_URL}/plants`)
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer token-abc')

    expect(plants).toEqual([
      { id: '11111111-1111-1111-1111-111111111111', name: 'Matriz — Telhado A', installedPowerKwp: '48.600' },
      { id: '22222222-2222-2222-2222-222222222222', name: 'Filial Norte', installedPowerKwp: null },
    ])
  })

  it('lança erro quando a resposta não é 200', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ detail: 'nope' }, 500))

    await expect(fetchPlants()).rejects.toThrow('Erro ao buscar usinas (500).')
  })

  it('lança erro quando o payload vem malformado', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ count: 1, items: [{ id: 'x' }] }))

    await expect(fetchPlants()).rejects.toThrow(/Resposta inválida da API/)
  })
})
