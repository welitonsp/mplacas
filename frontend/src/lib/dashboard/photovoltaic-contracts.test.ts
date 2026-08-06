import { describe, expect, it } from 'vitest'
import {
  baselineUnavailableMessage,
  lossesUnavailableMessage,
  parsePhotovoltaicSummary,
  performanceUnavailableMessage,
  ratioToPercent,
} from './photovoltaic-contracts'

function buildLossItems() {
  return [
    { category: 'COMMUNICATION', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'UNAVAILABILITY', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'CLIPPING', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'SOILING', evidence_level: 'POSSIBLE', estimated_loss_percent: '1.50', evidence_codes: ['SOILING_TREND'], limitation: null },
    { category: 'SHADING', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'TEMPERATURE', evidence_level: 'LIKELY', estimated_loss_percent: '2.30', evidence_codes: ['HIGH_CELL_TEMP'], limitation: null },
    { category: 'DEGRADATION', evidence_level: 'NOT_ASSESSABLE', estimated_loss_percent: null, evidence_codes: [], limitation: 'Baseline insuficiente.' },
    { category: 'UNEXPLAINED', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
  ]
}

function buildSummaryPayload(overrides: Record<string, unknown> = {}) {
  return {
    plant_id: '11111111-1111-1111-1111-111111111111',
    performance: {
      dc_capacity_kwp: '10.000',
      performance_ratio: '0.8200',
      temperature_corrected_performance_ratio: '0.8500',
      final_yield_kwh_per_kwp: '4.400',
      reporting_availability_ratio: '0.9800',
    },
    performance_unavailable_reason: null,
    baseline: {
      baseline_median_performance_ratio: '0.8000',
      clear_sky_poa_p90_kwh_m2: '5.500',
      degradation_percent: '-1.20',
      annualized_degradation_percent: '-0.60',
      degradation_status: 'STABLE',
    },
    baseline_unavailable_reason: null,
    reference_complete_on: null,
    losses: buildLossItems(),
    losses_unavailable_reason: null,
    expected_daily_production_kwh: '38.412',
    expected_daily_production_model_version: 'MPLACAS_EXPECTED_DAILY_PRODUCTION_V1',
    expected_daily_production_nature: 'SEASONAL_CLEAR_SKY_P90_ENVELOPE',
    expected_daily_production_unavailable_reason: null,
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

  it('faz parse de todos os campos técnicos quando todos os blocos estão presentes', () => {
    const summary = parsePhotovoltaicSummary(buildSummaryPayload())

    expect(summary.performance).toEqual({
      dc_capacity_kwp: '10.000',
      performance_ratio: '0.8200',
      temperature_corrected_performance_ratio: '0.8500',
      final_yield_kwh_per_kwp: '4.400',
      reporting_availability_ratio: '0.9800',
    })
    expect(summary.performance_unavailable_reason).toBeNull()

    expect(summary.baseline).toEqual({
      baseline_median_performance_ratio: '0.8000',
      clear_sky_poa_p90_kwh_m2: '5.500',
      degradation_percent: '-1.20',
      annualized_degradation_percent: '-0.60',
      degradation_status: 'STABLE',
    })

    expect(summary.losses).toHaveLength(8)
    expect(summary.losses?.map((item) => item.category)).toEqual([
      'COMMUNICATION',
      'UNAVAILABILITY',
      'CLIPPING',
      'SOILING',
      'SHADING',
      'TEMPERATURE',
      'DEGRADATION',
      'UNEXPLAINED',
    ])
    const soiling = summary.losses?.find((item) => item.category === 'SOILING')
    expect(soiling).toEqual({
      category: 'SOILING',
      evidence_level: 'POSSIBLE',
      estimated_loss_percent: '1.50',
      evidence_codes: ['SOILING_TREND'],
      limitation: null,
    })
    const degradation = summary.losses?.find((item) => item.category === 'DEGRADATION')
    expect(degradation?.evidence_level).toBe('NOT_ASSESSABLE')
    expect(degradation?.estimated_loss_percent).toBeNull()
    expect(degradation?.limitation).toBe('Baseline insuficiente.')
    expect(summary.losses_unavailable_reason).toBeNull()

    expect(summary.expectedProduction).toEqual({
      available: true,
      kwh: 38.412,
      modelVersion: 'MPLACAS_EXPECTED_DAILY_PRODUCTION_V1',
      nature: 'SEASONAL_CLEAR_SKY_P90_ENVELOPE',
    })
  })

  it('não lança exceção quando performance vem null — produz estado indisponível tipado', () => {
    const summary = parsePhotovoltaicSummary(
      buildSummaryPayload({ performance: null, performance_unavailable_reason: 'NO_PERFORMANCE_RESULTS' })
    )
    expect(summary.performance).toBeNull()
    expect(summary.performance_unavailable_reason).toBe('NO_PERFORMANCE_RESULTS')
  })

  it('não lança exceção quando losses vem null — produz estado indisponível tipado', () => {
    const summary = parsePhotovoltaicSummary(
      buildSummaryPayload({ losses: null, losses_unavailable_reason: 'NO_LOSS_ASSESSMENTS' })
    )
    expect(summary.losses).toBeNull()
    expect(summary.losses_unavailable_reason).toBe('NO_LOSS_ASSESSMENTS')
  })

  it('lança erro quando um item de losses tem categoria inválida', () => {
    const payload = buildSummaryPayload({
      losses: [{ category: 'NOT_A_CATEGORY', evidence_level: 'LIKELY', estimated_loss_percent: '1.0', evidence_codes: [], limitation: null }],
    })
    expect(() => parsePhotovoltaicSummary(payload)).toThrow(/category/)
  })
})

describe('ratioToPercent', () => {
  it('converte razão 0–1 para percentual', () => {
    expect(ratioToPercent('0.8200')).toBeCloseTo(82, 6)
  })

  it('retorna null para valor null', () => {
    expect(ratioToPercent(null)).toBeNull()
  })
})

describe('performanceUnavailableMessage / lossesUnavailableMessage', () => {
  it('produz mensagem específica quando performance está indisponível', () => {
    expect(performanceUnavailableMessage('NO_PERFORMANCE_RESULTS')).toContain('Desempenho técnico')
  })

  it('produz mensagem específica quando losses está indisponível', () => {
    expect(lossesUnavailableMessage('NO_LOSS_ASSESSMENTS')).toContain('causas de perda')
  })
})

describe('parsePhotovoltaicSummary — expectedProduction (ADR-068)', () => {
  it('estrutura os quatro campos novos quando a produção esperada está disponível', () => {
    const summary = parsePhotovoltaicSummary(buildSummaryPayload())
    expect(summary.expectedProduction).toEqual({
      available: true,
      kwh: 38.412,
      modelVersion: 'MPLACAS_EXPECTED_DAILY_PRODUCTION_V1',
      nature: 'SEASONAL_CLEAR_SKY_P90_ENVELOPE',
    })
  })

  it.each([
    ['NO_PERFORMANCE_HISTORY', null] as const,
    ['REFERENCE_YEAR_INCOMPLETE', '2027-03-14'] as const,
    ['INSUFFICIENT_SEASONAL_SAMPLES', null] as const,
    ['INCOMPLETE_EXPECTATION_INPUTS', null] as const,
  ])(
    'propaga o motivo %s quando o backend devolve os quatro campos como null + motivo',
    (reason, referenceCompleteOn) => {
      const summary = parsePhotovoltaicSummary(
        buildSummaryPayload({
          expected_daily_production_kwh: null,
          expected_daily_production_model_version: null,
          expected_daily_production_nature: null,
          expected_daily_production_unavailable_reason: reason,
          reference_complete_on: referenceCompleteOn,
        })
      )
      expect(summary.expectedProduction).toEqual({
        available: false,
        reason,
        referenceCompleteOn,
      })
    }
  )

  it('não inventa um número quando o kWh vem null mesmo sem um motivo explícito', () => {
    const summary = parsePhotovoltaicSummary(
      buildSummaryPayload({
        expected_daily_production_kwh: null,
        expected_daily_production_model_version: null,
        expected_daily_production_nature: null,
        expected_daily_production_unavailable_reason: null,
      })
    )
    expect(summary.expectedProduction.available).toBe(false)
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
    expect(baselineUnavailableMessage('INCOMPLETE_EXPECTATION_INPUTS', null)).toContain('incompletos')
  })
})
