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
          // Backend anterior à etapa 3 do ADR-083: sem datas nem medidor → null.
          cycleStart: null,
          cycleEnd: null,
          productionKwh: 1234.567,
          gridInjectionKwh: null,
          gridInjectionBasis: null,
          distributor: null,
          importedKwh: null,
          selfConsumptionKwh: null,
          quality: {
            missingDays: 0,
            provisionalDays: 1,
            incompleteDays: 0,
            unavailableDays: 0,
            // Snapshot anterior ao ADR-082: sem a chave de dias estimados.
            estimatedDays: null,
          },
        },
      ],
    })
  })

  it('lê datas do ciclo e o registro da distribuidora quando o backend envia', () => {
    const result = parseMonthlyProductionHistory(
      buildPayload({
        cycles: [
          buildCycle({
            cycle_start: '2026-08-17',
            cycle_end: '2026-09-14',
            grid_injection_kwh: '235',
            grid_injection_basis: 'METER',
            distributor: 'EQUATORIAL_GO',
            imported_kwh: '221',
            self_consumption_kwh: '348.210',
          }),
        ],
      }),
    )
    expect(result.cycles[0]).toMatchObject({
      cycleStart: '2026-08-17',
      cycleEnd: '2026-09-14',
      gridInjectionKwh: 235,
      gridInjectionBasis: 'METER',
      distributor: 'EQUATORIAL_GO',
      importedKwh: 221,
      selfConsumptionKwh: 348.21,
    })
  })

  it('origem da injeção desconhecida vira null, nunca medidor', () => {
    const result = parseMonthlyProductionHistory(
      buildPayload({ cycles: [buildCycle({ grid_injection_kwh: '235', grid_injection_basis: 'SOMETHING_NEW' })] }),
    )
    expect(result.cycles[0].gridInjectionBasis).toBeNull()
  })

  it('recusa data de ciclo malformada', () => {
    expect(() =>
      parseMonthlyProductionHistory(buildPayload({ cycles: [buildCycle({ cycle_start: '17/08/2026' })] })),
    ).toThrow(/cycle_start/)
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
