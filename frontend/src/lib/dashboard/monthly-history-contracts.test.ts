import { describe, expect, it } from 'vitest'
import { parseMonthlyProductionHistory } from './monthly-history-contracts'

function buildCycle(overrides: Record<string, unknown> = {}) {
  return {
    reference_month: '2026-05',
    bill_id: '11111111-1111-1111-1111-111111111111',
    status: 'STABLE',
    production_kwh: '1234.567',
    quality: {
      missing_days: 0,
      provisional_days: 1,
      incomplete_days: 0,
      unavailable_days: 0,
    },
    ...overrides,
  }
}

function buildPayload(overrides: Record<string, unknown> = {}) {
  return {
    plant_id: '22222222-2222-2222-2222-222222222222',
    limit: 12,
    cycles_returned: 1,
    cycles: [buildCycle()],
    ...overrides,
  }
}

describe('parseMonthlyProductionHistory', () => {
  it('faz parse de um payload válido com um ciclo completo', () => {
    const result = parseMonthlyProductionHistory(buildPayload())
    expect(result).toEqual({
      plantId: '22222222-2222-2222-2222-222222222222',
      limit: 12,
      cyclesReturned: 1,
      cycles: [
        {
          referenceMonth: '2026-05',
          billId: '11111111-1111-1111-1111-111111111111',
          status: 'STABLE',
          productionKwh: 1234.567,
          quality: {
            missingDays: 0,
            provisionalDays: 1,
            incompleteDays: 0,
            unavailableDays: 0,
          },
        },
      ],
    })
  })

  it('faz parse de production_kwh: null sem fabricar 0', () => {
    const result = parseMonthlyProductionHistory(
      buildPayload({ cycles: [buildCycle({ production_kwh: null })] })
    )
    expect(result.cycles[0].productionKwh).toBeNull()
  })

  it('faz parse de quality: null (snapshot sem nenhuma das chaves)', () => {
    const result = parseMonthlyProductionHistory(
      buildPayload({ cycles: [buildCycle({ quality: null })] })
    )
    expect(result.cycles[0].quality).toBeNull()
  })

  it('faz parse de lista de ciclos vazia (usina sem ciclo fechado)', () => {
    const result = parseMonthlyProductionHistory(
      buildPayload({ cycles_returned: 0, cycles: [] })
    )
    expect(result.cycles).toEqual([])
    expect(result.cyclesReturned).toBe(0)
  })

  it('lança para payload malformado (não-objeto)', () => {
    expect(() => parseMonthlyProductionHistory(null)).toThrow('Resposta inválida da API.')
    expect(() => parseMonthlyProductionHistory('oops')).toThrow('Resposta inválida da API.')
  })

  it('lança para payload malformado (cycles ausente/não-array)', () => {
    expect(() => parseMonthlyProductionHistory(buildPayload({ cycles: null }))).toThrow(
      'Resposta inválida da API: cycles'
    )
  })

  it('lança para ciclo malformado (reference_month ausente)', () => {
    expect(() =>
      parseMonthlyProductionHistory(
        buildPayload({ cycles: [buildCycle({ reference_month: undefined })] })
      )
    ).toThrow('Resposta inválida da API: reference_month')
  })

  it('lança para production_kwh que não é string nem null', () => {
    expect(() =>
      parseMonthlyProductionHistory(
        buildPayload({ cycles: [buildCycle({ production_kwh: 1234.567 })] })
      )
    ).toThrow('Resposta inválida da API: production_kwh')
  })
})
