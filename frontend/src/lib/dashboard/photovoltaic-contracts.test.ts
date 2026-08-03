import { describe, expect, it } from 'vitest'
import {
  baselineUnavailableMessage,
  deriveExpectedDailyProduction,
  parsePhotovoltaicSummary,
} from './photovoltaic-contracts'

function buildSummaryPayload(overrides: Record<string, unknown> = {}) {
  return {
    plant_id: '11111111-1111-1111-1111-111111111111',
    performance: { dc_capacity_kwp: '10.000' },
    performance_unavailable_reason: null,
    baseline: {
      baseline_median_performance_ratio: '0.8000',
      clear_sky_poa_p90_kwh_m2: '5.500',
    },
    baseline_unavailable_reason: null,
    reference_complete_on: null,
    losses: null,
    losses_unavailable_reason: 'NO_LOSS_ASSESSMENTS',
    ...overrides,
  }
}

describe('parsePhotovoltaicSummary', () => {
  it('faz parse de um resumo com baseline disponível', () => {
    const summary = parsePhotovoltaicSummary(buildSummaryPayload())
    expect(summary.plant_id).toBe('11111111-1111-1111-1111-111111111111')
    expect(summary.performance?.dc_capacity_kwp).toBe('10.000')
    expect(summary.baseline?.clear_sky_poa_p90_kwh_m2).toBe('5.500')
    expect(summary.baseline_unavailable_reason).toBeNull()
  })

  it('faz parse do motivo de indisponibilidade REFERENCE_YEAR_INCOMPLETE com a data', () => {
    const summary = parsePhotovoltaicSummary(
      buildSummaryPayload({
        baseline: null,
        baseline_unavailable_reason: 'REFERENCE_YEAR_INCOMPLETE',
        reference_complete_on: '2027-03-14',
      })
    )
    expect(summary.baseline).toBeNull()
    expect(summary.baseline_unavailable_reason).toBe('REFERENCE_YEAR_INCOMPLETE')
    expect(summary.reference_complete_on).toBe('2027-03-14')
  })

  it('lança erro para payload que não é um objeto', () => {
    expect(() => parsePhotovoltaicSummary(null)).toThrow('Resposta inválida da API.')
  })

  it('lança erro quando plant_id está ausente', () => {
    const payload = buildSummaryPayload()
    delete (payload as Record<string, unknown>).plant_id
    expect(() => parsePhotovoltaicSummary(payload)).toThrow(/plant_id/)
  })
})

describe('deriveExpectedDailyProduction', () => {
  it('calcula kWh esperado a partir de dc_capacity_kwp × baseline sazonal', () => {
    const summary = parsePhotovoltaicSummary(buildSummaryPayload())
    const result = deriveExpectedDailyProduction(summary)
    expect(result.available).toBe(true)
    if (result.available) {
      // 10 kWp * 5.5 kWh/m2 * 0.8 = 44
      expect(result.kwh).toBeCloseTo(44, 6)
    }
  })

  it.each([
    ['NO_PERFORMANCE_HISTORY', null] as const,
    ['REFERENCE_YEAR_INCOMPLETE', '2027-03-14'] as const,
    ['INSUFFICIENT_SEASONAL_SAMPLES', null] as const,
  ])('propaga o motivo %s quando o baseline está indisponível', (reason, referenceCompleteOn) => {
    const summary = parsePhotovoltaicSummary(
      buildSummaryPayload({
        baseline: null,
        baseline_unavailable_reason: reason,
        reference_complete_on: referenceCompleteOn,
      })
    )
    const result = deriveExpectedDailyProduction(summary)
    expect(result.available).toBe(false)
    if (!result.available) {
      expect(result.reason).toBe(reason)
      expect(result.referenceCompleteOn).toBe(referenceCompleteOn)
    }
  })

  it('não inventa um número quando dc_capacity_kwp está ausente apesar do baseline existir', () => {
    const summary = parsePhotovoltaicSummary(
      buildSummaryPayload({ performance: null, performance_unavailable_reason: 'NO_PERFORMANCE_RESULTS' })
    )
    const result = deriveExpectedDailyProduction(summary)
    expect(result.available).toBe(false)
  })
})

describe('baselineUnavailableMessage', () => {
  it('menciona a data de referência quando REFERENCE_YEAR_INCOMPLETE tem reference_complete_on', () => {
    const message = baselineUnavailableMessage('REFERENCE_YEAR_INCOMPLETE', '2027-03-14')
    expect(message).toContain('14/03/2027')
  })

  it('produz uma mensagem específica para cada motivo', () => {
    expect(baselineUnavailableMessage('NO_PERFORMANCE_HISTORY', null)).toContain('histórico')
    expect(baselineUnavailableMessage('INSUFFICIENT_SEASONAL_SAMPLES', null)).toContain('sazonais')
  })
})
