import { describe, expect, it } from 'vitest'
import { parsePlantsResponse } from './plant-contracts'

function buildPayload(overrides: Record<string, unknown> = {}) {
  return {
    count: 2,
    items: [
      { id: '11111111-1111-1111-1111-111111111111', name: 'Matriz — Telhado A', installed_power_kwp: '48.600' },
      { id: '22222222-2222-2222-2222-222222222222', name: 'Filial Norte', installed_power_kwp: null },
    ],
    ...overrides,
  }
}

describe('parsePlantsResponse', () => {
  it('faz parse de um payload válido com itens variados, incluindo installed_power_kwp null', () => {
    const result = parsePlantsResponse(buildPayload())
    expect(result.count).toBe(2)
    expect(result.items).toEqual([
      { id: '11111111-1111-1111-1111-111111111111', name: 'Matriz — Telhado A', installedPowerKwp: '48.600' },
      { id: '22222222-2222-2222-2222-222222222222', name: 'Filial Norte', installedPowerKwp: null },
    ])
  })

  it('faz parse de uma lista vazia (count 0)', () => {
    const result = parsePlantsResponse({ count: 0, items: [] })
    expect(result.count).toBe(0)
    expect(result.items).toEqual([])
  })

  it('lança erro para payload que não é um objeto', () => {
    expect(() => parsePlantsResponse(null)).toThrow('Resposta inválida da API.')
    expect(() => parsePlantsResponse('oops')).toThrow('Resposta inválida da API.')
  })

  it('lança erro quando items está ausente', () => {
    const payload = buildPayload()
    delete (payload as Record<string, unknown>).items
    expect(() => parsePlantsResponse(payload)).toThrow(/items/)
  })

  it('lança erro quando count não é número', () => {
    expect(() => parsePlantsResponse(buildPayload({ count: '2' }))).toThrow(/count/)
  })

  it('lança erro quando um item não tem id', () => {
    const payload = buildPayload({
      items: [{ name: 'Sem id', installed_power_kwp: null }],
    })
    expect(() => parsePlantsResponse(payload)).toThrow(/id/)
  })

  it('lança erro quando um item não tem name', () => {
    const payload = buildPayload({
      items: [{ id: '11111111-1111-1111-1111-111111111111', installed_power_kwp: null }],
    })
    expect(() => parsePlantsResponse(payload)).toThrow(/name/)
  })

  it('lança erro quando installed_power_kwp tem tipo errado', () => {
    const payload = buildPayload({
      items: [{ id: '11111111-1111-1111-1111-111111111111', name: 'Usina', installed_power_kwp: 48.6 }],
    })
    expect(() => parsePlantsResponse(payload)).toThrow(/installed_power_kwp/)
  })
})
