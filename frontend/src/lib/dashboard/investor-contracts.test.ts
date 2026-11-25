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
    expect(panel.premises?.inverterReplacementYears).toEqual([12, 24])
    expect(panel.projection?.baselineCycles).toBe(1)
    expect(panel.projection?.annualSavingOverInvestment).toBe('0.2829')
    expect(panel.projection?.irrSpreadOverCdiPerYear).toBe('0.1958')
    expect(panel.projection?.patrimony[25].solarPathRealBrl).not.toBeNull()
  })

  it('backend antigo (sem os campos novos) vira null, nunca zero', () => {
    const { baseline_cycles: _a, annual_saving_over_investment: _b, irr_spread_over_cdi_per_year: _c, ...legacyProjection } =
      investorAvailablePayload.projection
    const { inverter_replacement_years: _d, ...legacyPremises } = investorAvailablePayload.premises
    const panel = parseInvestorPanel({
      ...investorAvailablePayload,
      projection: {
        ...legacyProjection,
        patrimony: [{ year: 0, cdi_path_brl: '11200', solar_path_brl: '0' }],
      },
      premises: legacyPremises,
    })
    expect(panel.projection?.baselineCycles).toBeNull()
    expect(panel.projection?.annualSavingOverInvestment).toBeNull()
    expect(panel.projection?.irrSpreadOverCdiPerYear).toBeNull()
    expect(panel.projection?.patrimony[0].cdiPathRealBrl).toBeNull()
    expect(panel.premises?.inverterReplacementYears).toEqual([12])
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
