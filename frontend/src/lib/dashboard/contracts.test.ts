import { describe, expect, it } from 'vitest'
import {
  classifyAnomalyErrorStatus,
  latestNonNullProductionDate,
  type AnomalyDailyPoint,
} from './contracts'

function buildDaily(overrides: Partial<AnomalyDailyPoint> = {}): AnomalyDailyPoint {
  return {
    date: '2026-08-01',
    actual_production_kwh: 40,
    expected_production_kwh: 44,
    level: 'NORMAL',
    deviation_percent: -9,
    irradiation_kwh_m2: null,
    ...overrides,
  }
}

describe('classifyAnomalyErrorStatus', () => {
  it('classifica 404 como ausência de dado coletado, não como falha do sistema', () => {
    expect(classifyAnomalyErrorStatus(404)).toBe('NOT_FOUND')
  })

  it('classifica 500 como falha do sistema', () => {
    expect(classifyAnomalyErrorStatus(500)).toBe('SERVER_ERROR')
  })

  it('classifica 401 como null (sessão expirada, tratada à parte)', () => {
    expect(classifyAnomalyErrorStatus(401)).toBeNull()
  })
})

describe('latestNonNullProductionDate', () => {
  it('retorna a data do último dia com produção não nula', () => {
    const daily = [
      buildDaily({ date: '2026-07-30', actual_production_kwh: 38 }),
      buildDaily({ date: '2026-07-31', actual_production_kwh: 41 }),
      buildDaily({ date: '2026-08-01', actual_production_kwh: null }),
    ]

    expect(latestNonNullProductionDate(daily)).toBe('2026-07-31')
  })

  it('retorna null quando nenhum dia tem produção coletada', () => {
    const daily = [buildDaily({ actual_production_kwh: null })]

    expect(latestNonNullProductionDate(daily)).toBeNull()
  })

  it('retorna null para lista vazia', () => {
    expect(latestNonNullProductionDate([])).toBeNull()
  })
})
