import { describe, expect, it } from 'vitest'
import { parseBill, parseBillEnvelope, parsePendingBills } from './bill-contracts'

const validBill = {
  id: 'bill-1',
  plant_id: 'plant-1',
  distributor: 'EQUATORIAL_GO',
  reference_month: '2026-09',
  cycle_start: '2026-08-17',
  cycle_end: '2026-09-14',
  billed_days: 29,
  imported_kwh: '221.00',
  injected_kwh: '221.00',
  compensated_kwh: '221.00',
  credit_balance_kwh: '17.98',
  total_amount_brl: '70.22',
  public_lighting_brl: '30.21',
  generation_cycle_kwh: '235.00',
  tariff_with_taxes_brl_kwh: '0.787589',
  tariff_without_taxes_brl_kwh: '0.613030',
  wire_b_tariff_brl_kwh: '0.175126',
  status: 'PENDING_REVIEW',
  created_at: null,
  reviewed_at: null,
}

describe('bill-contracts', () => {
  it('lê uma fatura válida mantendo os valores como string', () => {
    const bill = parseBill(validBill)
    expect(bill.referenceMonth).toBe('2026-09')
    expect(bill.totalAmountBrl).toBe('70.22')
    expect(bill.generationCycleKwh).toBe('235.00')
    expect(bill.status).toBe('PENDING_REVIEW')
  })

  it('campos opcionais null (ou ausentes) viram null, nunca zero', () => {
    const withNulls = parseBill({ ...validBill, generation_cycle_kwh: null, wire_b_tariff_brl_kwh: undefined })
    expect(withNulls.generationCycleKwh).toBeNull()
    expect(withNulls.wireBTariffBrlKwh).toBeNull()
  })

  it('recusa payload malformado', () => {
    expect(() => parseBill({ ...validBill, total_amount_brl: 70.22 })).toThrow(/total_amount_brl/)
    expect(() => parseBill({ ...validBill, status: 'DESCONHECIDO' })).toThrow(/status/)
    expect(() => parseBill({ ...validBill, billed_days: '29' })).toThrow(/billed_days/)
    expect(() => parseBill(null)).toThrow()
  })

  it('lê a lista de pendentes e o envelope das ações', () => {
    expect(parsePendingBills({ count: 1, items: [validBill] }).items).toHaveLength(1)
    expect(() => parsePendingBills({ count: 1 })).toThrow(/items/)
    expect(parseBillEnvelope({ status: 'confirmed', bill: { ...validBill, status: 'CONFIRMED' } }).status).toBe(
      'CONFIRMED',
    )
  })
})
