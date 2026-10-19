import { describe, expect, it } from 'vitest'
import { parseInvestorPanel } from './investor-contracts'
import { investorAvailablePayload } from '../../test/investorFixtures'
import { investorUnavailablePayload } from '../../test/dashboardFixtures'

describe('investor-contracts', () => {
  it('lê o painel completo mantendo números como string', () => {
    const panel = parseInvestorPanel(investorAvailablePayload)
    expect(panel.unavailableReason).toBeNull()
    expect(panel.projection?.irrPerYear).toBe('0.3290')
    expect(panel.projection?.paybackSimpleMonths).toBe(44)
    expect(panel.projection?.patrimony).toHaveLength(26)
    expect(panel.realized?.cyclesCounted).toBe(1)
    expect(panel.premises?.inverterReplacementYear).toBe(12)
  })

  it('lê o estado indisponível com blocos nulos', () => {
    const panel = parseInvestorPanel(investorUnavailablePayload)
    expect(panel.unavailableReason).toBe('INVESTMENT_NOT_REGISTERED')
    expect(panel.projection).toBeNull()
    expect(panel.realized).toBeNull()
  })

  it('recusa payload malformado', () => {
    expect(() => parseInvestorPanel({ ...investorUnavailablePayload, unavailable_reason: 'OUTRO' })).toThrow(
      /unavailable_reason/,
    )
    expect(() =>
      parseInvestorPanel({
        ...investorAvailablePayload,
        projection: { ...investorAvailablePayload.projection, payback_simple_months: '44' },
      }),
    ).toThrow(/payback_simple_months/)
    expect(() => parseInvestorPanel({ ...investorAvailablePayload, calculation_versions: [3] })).toThrow(
      /calculation_versions/,
    )
  })
})
