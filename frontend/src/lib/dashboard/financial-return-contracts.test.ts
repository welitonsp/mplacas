import { describe, expect, it } from 'vitest'
import {
  coverageLabel,
  financialReturnUnavailableMessage,
  hasPartialCoverage,
  isPaybackAlreadyReached,
  parseFinancialConfiguration,
  parseFinancialReturn,
  paybackUnavailableMessage,
} from './financial-return-contracts'

function buildPayload(overrides: Record<string, unknown> = {}) {
  return {
    plant_id: '11111111-1111-1111-1111-111111111111',
    investment_amount_brl: '48000.00',
    investment_recorded_on: '2024-03-11',
    commissioned_on: '2024-03-01',
    accumulated_savings_brl: '9120.55',
    average_monthly_savings_brl: '760.05',
    cycles_counted: 12,
    cycles_expected: 17,
    roi_percent: '19.0',
    payback_projection_months: 64,
    unavailable_reason: null,
    payback_unavailable_reason: null,
    ...overrides,
  }
}

describe('parseFinancialReturn', () => {
  it('faz parse de um payload completo', () => {
    const result = parseFinancialReturn(buildPayload())
    expect(result).toEqual({
      plant_id: '11111111-1111-1111-1111-111111111111',
      investment_amount_brl: '48000.00',
      investment_recorded_on: '2024-03-11',
      commissioned_on: '2024-03-01',
      accumulated_savings_brl: '9120.55',
      average_monthly_savings_brl: '760.05',
      cycles_counted: 12,
      cycles_expected: 17,
      roi_percent: '19.0',
      payback_projection_months: 64,
      unavailable_reason: null,
      payback_unavailable_reason: null,
    })
  })

  it('faz parse de INVESTMENT_NOT_REGISTERED sem lançar exceção, com todos os campos derivados nulos', () => {
    const result = parseFinancialReturn(
      buildPayload({
        investment_amount_brl: null,
        investment_recorded_on: null,
        accumulated_savings_brl: null,
        average_monthly_savings_brl: null,
        cycles_counted: null,
        cycles_expected: null,
        roi_percent: null,
        payback_projection_months: null,
        unavailable_reason: 'INVESTMENT_NOT_REGISTERED',
        payback_unavailable_reason: null,
      })
    )
    expect(result.unavailable_reason).toBe('INVESTMENT_NOT_REGISTERED')
    expect(result.investment_amount_brl).toBeNull()
    expect(result.roi_percent).toBeNull()
    expect(result.payback_projection_months).toBeNull()
  })

  it('faz parse de NO_CONSOLIDATED_SAVINGS sem lançar exceção', () => {
    const result = parseFinancialReturn(
      buildPayload({
        accumulated_savings_brl: null,
        average_monthly_savings_brl: null,
        cycles_counted: 0,
        roi_percent: null,
        payback_projection_months: null,
        unavailable_reason: 'NO_CONSOLIDATED_SAVINGS',
        payback_unavailable_reason: null,
      })
    )
    expect(result.unavailable_reason).toBe('NO_CONSOLIDATED_SAVINGS')
    expect(result.cycles_counted).toBe(0)
    expect(result.accumulated_savings_brl).toBeNull()
    expect(result.roi_percent).toBeNull()
  })

  it('faz parse de INSUFFICIENT_HISTORY (payback) sem lançar exceção, mantendo o ROI', () => {
    const result = parseFinancialReturn(
      buildPayload({
        cycles_counted: 3,
        payback_projection_months: null,
        unavailable_reason: null,
        payback_unavailable_reason: 'INSUFFICIENT_HISTORY',
      })
    )
    expect(result.unavailable_reason).toBeNull()
    expect(result.roi_percent).toBe('19.0')
    expect(result.payback_unavailable_reason).toBe('INSUFFICIENT_HISTORY')
    expect(result.payback_projection_months).toBeNull()
  })

  it('lança para payload que não é um objeto', () => {
    expect(() => parseFinancialReturn(null)).toThrow()
    expect(() => parseFinancialReturn('oops')).toThrow()
  })

  it('lança quando plant_id está ausente', () => {
    const payload = buildPayload()
    delete (payload as Record<string, unknown>).plant_id
    expect(() => parseFinancialReturn(payload)).toThrow()
  })
})

describe('parseFinancialConfiguration', () => {
  it('faz parse da configuração financeira', () => {
    const result = parseFinancialConfiguration({
      plant_id: '11111111-1111-1111-1111-111111111111',
      investment_amount_brl: '48000.00',
      investment_recorded_on: '2024-03-11',
    })
    expect(result.investment_amount_brl).toBe('48000.00')
  })

  it('aceita investment_amount_brl nulo sem lançar exceção', () => {
    const result = parseFinancialConfiguration({
      plant_id: '11111111-1111-1111-1111-111111111111',
      investment_amount_brl: null,
      investment_recorded_on: null,
    })
    expect(result.investment_amount_brl).toBeNull()
  })
})

describe('coverageLabel / hasPartialCoverage', () => {
  it('indica cobertura parcial quando cycles_counted < cycles_expected', () => {
    const result = parseFinancialReturn(buildPayload({ cycles_counted: 12, cycles_expected: 17 }))
    expect(hasPartialCoverage(result)).toBe(true)
    expect(coverageLabel(result)).toBe('Baseado em 12 de 17 ciclos com relatório consolidado.')
  })

  it('não indica cobertura parcial quando os ciclos coincidem', () => {
    const result = parseFinancialReturn(buildPayload({ cycles_counted: 17, cycles_expected: 17 }))
    expect(hasPartialCoverage(result)).toBe(false)
    expect(coverageLabel(result)).toBeNull()
  })

  it('não indica cobertura parcial quando cycles_expected é nulo', () => {
    const result = parseFinancialReturn(buildPayload({ cycles_expected: null }))
    expect(hasPartialCoverage(result)).toBe(false)
  })
})

describe('isPaybackAlreadyReached', () => {
  it('identifica payback já atingido quando payback_projection_months == cycles_counted', () => {
    const result = parseFinancialReturn(
      buildPayload({ cycles_counted: 20, payback_projection_months: 20 })
    )
    expect(isPaybackAlreadyReached(result)).toBe(true)
  })

  it('não identifica payback atingido quando a projeção está no futuro', () => {
    const result = parseFinancialReturn(
      buildPayload({ cycles_counted: 12, payback_projection_months: 64 })
    )
    expect(isPaybackAlreadyReached(result)).toBe(false)
  })
})

describe('financialReturnUnavailableMessage / paybackUnavailableMessage', () => {
  it('tem mensagem específica para os três motivos', () => {
    expect(financialReturnUnavailableMessage('INVESTMENT_NOT_REGISTERED')).toMatch(/cadastre/i)
    expect(financialReturnUnavailableMessage('NO_CONSOLIDATED_SAVINGS')).toMatch(/economia calculada/i)
    expect(paybackUnavailableMessage('INSUFFICIENT_HISTORY')).toMatch(/6 ciclos/)
  })
})
