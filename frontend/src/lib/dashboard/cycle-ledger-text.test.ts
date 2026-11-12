import { describe, expect, it } from 'vitest'
import { parseCycleLedger, type SavingsWindow } from './cycle-ledger-contracts'
import {
  formatCalculatedOn,
  isNegativeMoney,
  ledgerExclusionText,
  ledgerExtraSeals,
  ledgerLeftOutNote,
  ledgerQualityNote,
  ledgerReasonText,
  ledgerTotalLine,
} from './cycle-ledger-text'

const win = (over: Partial<SavingsWindow> = {}): SavingsWindow => ({
  totalEstimatedSavingsBrl: '1234.50',
  cyclesInWindow: 12,
  cyclesWithSavings: 9,
  cyclesWithoutSavings: 0,
  cyclesExcludedCommissioning: 0,
  cyclesSupersededByRebilling: 0,
  commissioningKnown: true,
  firstReferenceMonth: '2025-08',
  lastReferenceMonth: '2026-07',
  cyclesWithBillTariff: 0,
  cyclesWithOutdatedOrPartial: 0,
  ...over,
})
const cycle = (over: Record<string, unknown> = {}) =>
  parseCycleLedger({ cycles: [{ reference_month: '2026-05', bill_id: 'b', estimated_savings_brl: '10.00', ...over }] }).cycles[0]

describe('texto da conta ciclo a ciclo', () => {
  it('linha do total com contadores e período', () => {
    expect(ledgerTotalLine(win())).toMatch(/^Economia estimada somada: R\$\s1\.234,50, em 9 de 12 ciclos \(ago\/25 a jul\/26\)$/)
    expect(ledgerTotalLine(win())).not.toMatch(/acumulad/i)
  })
  it('total nulo: sem R$ e sem zero', () => {
    const line = ledgerTotalLine(win({ totalEstimatedSavingsBrl: null, cyclesWithSavings: 0 }))
    expect(line).toBe('Nenhum ciclo do período tem economia calculada, por isso não há soma.')
    expect(line).not.toMatch(/R\$/)
  })
  it('um só ciclo no período usa singular e um só mês', () => {
    const line = ledgerTotalLine(win({ cyclesInWindow: 1, cyclesWithSavings: 1, firstReferenceMonth: '2026-07' }))
    expect(line).toMatch(/em 1 de 1 ciclo \(jul\/26\)$/)
  })
  it('o que ficou fora só aparece com contador > 0', () => {
    expect(ledgerLeftOutNote(win())).toBeNull()
    const note = ledgerLeftOutNote(win({ cyclesExcludedCommissioning: 2, cyclesSupersededByRebilling: 1, cyclesWithoutSavings: 3 }))
    expect(note).toContain('2 ciclos do mês da ligação da usina ou anteriores')
    expect(note).toContain('1 cálculo de mês refaturado')
    expect(note).toContain('3 ciclos sem economia calculada')
  })
  it('nota de qualidade da soma', () => {
    expect(ledgerQualityNote(win())).toBeNull()
    expect(ledgerQualityNote(win({ cyclesWithBillTariff: 1, cyclesWithOutdatedOrPartial: 2 }))).toBe(
      'Dentro da soma, 1 ciclo usa a tarifa da própria fatura e 2 ciclos foram calculados pela fórmula antiga ou com dias sem leitura do inversor: o total pode estar subestimado.',
    )
  })
  it('motivos tipados viram palavras, nunca R$', () => {
    for (const reason of ['NO_PRODUCTION_DATA', 'TARIFF_NOT_AVAILABLE', 'NO_CONSUMPTION_DATA', 'REPORT_PREDATES_SAVINGS', 'SAVINGS_UNAVAILABLE', 'API_WITHOUT_SAVINGS', 'OUTRO', null]) {
      expect(ledgerReasonText(reason)).toMatch(/[a-z]{4,}/)
      expect(ledgerReasonText(reason)).not.toMatch(/R\$|0,00/)
    }
  })
  it('selos extras só com economia', () => {
    expect(ledgerExtraSeals(cycle())).toEqual([])
    expect(ledgerExtraSeals(cycle({ savings_tariff_source: 'BILL_TARIFF', savings_gap_cause: 'PARTIAL_PRODUCTION' }))).toHaveLength(2)
    expect(ledgerExtraSeals(cycle({ savings_gap_cause: 'OUTDATED_CALCULATION' }))[0]).toMatch(/fórmula antiga/)
    expect(ledgerExtraSeals(cycle({ estimated_savings_brl: null, savings_tariff_source: 'BILL_TARIFF' }))).toEqual([])
  })
  it('exclusão da soma, com precedência', () => {
    expect(ledgerExclusionText(cycle())).toBeNull()
    expect(ledgerExclusionText(cycle({ is_commissioning_month: true }))).toMatch(/Não entra na soma: mês da ligação/)
    expect(ledgerExclusionText(cycle({ is_before_commissioning: true }))).toMatch(/anterior à ligação/)
    expect(ledgerExclusionText(cycle({ superseded_by_rebilling: true, is_commissioning_month: true }))).toMatch(/refaturado/)
  })
  it('negativo e data', () => {
    expect(isNegativeMoney('-1.00')).toBe(true)
    expect(isNegativeMoney('1.00')).toBe(false)
    expect(isNegativeMoney(null)).toBe(false)
    expect(formatCalculatedOn('2026-08-20T15:00:00+00:00')).toBe('20/08/2026')
    expect(formatCalculatedOn('2026-08-20T01:00:00+00:00')).toBe('19/08/2026')
    expect(formatCalculatedOn('lixo')).toBeNull()
    expect(formatCalculatedOn(null)).toBeNull()
  })
})
