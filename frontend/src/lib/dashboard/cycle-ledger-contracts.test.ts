import { describe, expect, it } from 'vitest'
import { cycleLedgerPayload } from '../../test/dashboardFixtures'
import { LEDGER_API_WITHOUT_SAVINGS, parseCycleLedger } from './cycle-ledger-contracts'

const base = { reference_month: '2026-05', bill_id: 'b1' }
const clone = () => structuredClone(cycleLedgerPayload)

describe('parseCycleLedger', () => {
  it('payload válido: valores como texto, do mais recente ao mais antigo, janela lida', () => {
    const ledger = parseCycleLedger(cycleLedgerPayload)
    expect(ledger.cycles.map((c) => c.referenceMonth)).toEqual(['2026-07', '2026-06'])
    expect(ledger.cycles[0].estimatedSavingsBrl).toBe('300.40')
    expect(ledger.cycles[0].billTotalAmountBrl).toBe('210.00')
    expect(ledger.cycles[0].savingsTariffSource).toBe('DISTRIBUTOR_FULL_TARIFF')
    expect(ledger.window?.totalEstimatedSavingsBrl).toBe('550.50')
    expect(ledger.window?.cyclesInWindow).toBe(2)
    expect(ledger.window?.commissioningKnown).toBe(true)
  })

  it('economia negativa é preservada, não truncada', () => {
    const payload = { cycles: [{ ...base, estimated_savings_brl: '-12.30' }] }
    expect(parseCycleLedger(payload).cycles[0].estimatedSavingsBrl).toBe('-12.30')
  })

  it('economia nula com motivo: indisponível, motivo preservado, sem zero', () => {
    const payload = {
      cycles: [{ ...base, estimated_savings_brl: null, savings_unavailable_reason: 'TARIFF_NOT_AVAILABLE', savings_gap_cause: 'SAVINGS_UNAVAILABLE' }],
    }
    const cycle = parseCycleLedger(payload).cycles[0]
    expect(cycle.estimatedSavingsBrl).toBeNull()
    expect(cycle.savingsUnavailableReason).toBe('TARIFF_NOT_AVAILABLE')
    expect(cycle.savingsGapCause).toBe('SAVINGS_UNAVAILABLE')
  })

  it('economia nula sem motivo, com a chave presente: SAVINGS_UNAVAILABLE', () => {
    const cycle = parseCycleLedger({ cycles: [{ ...base, estimated_savings_brl: null }] }).cycles[0]
    expect(cycle.savingsUnavailableReason).toBe('SAVINGS_UNAVAILABLE')
  })

  it('payload de API antiga (sem campos novos): indisponível, janela nula, sem erro', () => {
    const ledger = parseCycleLedger({ cycles: [base] })
    const cycle = ledger.cycles[0]
    expect(cycle.estimatedSavingsBrl).toBeNull()
    expect(cycle.savingsUnavailableReason).toBe(LEDGER_API_WITHOUT_SAVINGS)
    expect(cycle.billTotalAmountBrl).toBeNull()
    expect(cycle.supersededByRebilling).toBe(false)
    expect(cycle.isCommissioningMonth).toBeNull()
    expect(ledger.window).toBeNull()
  })

  it('causa/origem desconhecidas viram null; ciclos vazios são aceitos', () => {
    const cycle = parseCycleLedger({
      cycles: [{ ...base, estimated_savings_brl: '1.00', savings_tariff_source: 'NOVA', savings_gap_cause: 'NOVA' }],
    }).cycles[0]
    expect(cycle.savingsTariffSource).toBeNull()
    expect(cycle.savingsGapCause).toBeNull()
    expect(parseCycleLedger({ cycles: [] }).cycles).toEqual([])
  })

  it('janela com total nulo preserva null', () => {
    const payload = clone()
    payload.savings_window.total_estimated_savings_brl = null as unknown as string
    expect(parseCycleLedger(payload).window?.totalEstimatedSavingsBrl).toBeNull()
  })

  it.each([
    ['não é objeto', 'x'],
    ['cycles ausente', {}],
    ['ciclo sem bill_id', { cycles: [{ reference_month: '2026-05' }] }],
    ['economia como número', { cycles: [{ ...base, estimated_savings_brl: 10 }] }],
    ['economia ilegível', { cycles: [{ ...base, estimated_savings_brl: 'abc' }] }],
    ['fatura com tipo errado', { cycles: [{ ...base, bill_total_amount_brl: 5 }] }],
    ['superseded_by_rebilling com tipo errado', { cycles: [{ ...base, superseded_by_rebilling: 'sim' }] }],
    ['booleano com tipo errado', { cycles: [{ ...base, is_commissioning_month: 'sim' }] }],
    ['janela com contador inválido', { cycles: [], savings_window: { cycles_in_window: 'x' } }],
  ])('malformado (%s) lança', (_name, payload) => {
    expect(() => parseCycleLedger(payload)).toThrow()
  })
})
