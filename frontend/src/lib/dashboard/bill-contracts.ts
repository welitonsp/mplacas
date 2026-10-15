// Parser do contrato de faturas (`/billing/intake-pdf`, `/billing/pending`,
// `/billing/{id}/confirm|reject`, ver `billing/router.py::_serialize`).
//
// Valores numéricos chegam como string (`Decimal` serializado) e ficam como
// string aqui — convertidos só na hora de exibir, igual ao resto do dashboard.
// Os quatro campos opcionais da fatura SCEE (geração no medidor e tarifas)
// podem vir `null` quando a fatura não os traz: nunca viram `0`.

export type BillStatus = 'PENDING_REVIEW' | 'CONFIRMED' | 'REJECTED'

export interface UtilityBill {
  id: string
  plantId: string
  distributor: string
  referenceMonth: string
  cycleStart: string
  cycleEnd: string
  billedDays: number
  importedKwh: string
  injectedKwh: string
  compensatedKwh: string
  creditBalanceKwh: string
  totalAmountBrl: string
  publicLightingBrl: string
  generationCycleKwh: string | null
  tariffWithTaxesBrlKwh: string | null
  tariffWithoutTaxesBrlKwh: string | null
  wireBTariffBrlKwh: string | null
  status: BillStatus
}

export interface PendingBills {
  count: number
  items: UtilityBill[]
}

const STATUSES: readonly BillStatus[] = ['PENDING_REVIEW', 'CONFIRMED', 'REJECTED']

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireString(source: Record<string, unknown>, key: string): string {
  const value = source[key]
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value
}

function nullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  // Ausente (backend anterior a estes campos) é tratado como `null`, não erro.
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function requireNumber(source: Record<string, unknown>, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

export function parseBill(value: unknown): UtilityBill {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: bill')
  const status = requireString(value, 'status')
  if (!(STATUSES as readonly string[]).includes(status)) {
    throw new Error('Resposta inválida da API: status')
  }
  return {
    id: requireString(value, 'id'),
    plantId: requireString(value, 'plant_id'),
    distributor: requireString(value, 'distributor'),
    referenceMonth: requireString(value, 'reference_month'),
    cycleStart: requireString(value, 'cycle_start'),
    cycleEnd: requireString(value, 'cycle_end'),
    billedDays: requireNumber(value, 'billed_days'),
    importedKwh: requireString(value, 'imported_kwh'),
    injectedKwh: requireString(value, 'injected_kwh'),
    compensatedKwh: requireString(value, 'compensated_kwh'),
    creditBalanceKwh: requireString(value, 'credit_balance_kwh'),
    totalAmountBrl: requireString(value, 'total_amount_brl'),
    publicLightingBrl: requireString(value, 'public_lighting_brl'),
    generationCycleKwh: nullableString(value, 'generation_cycle_kwh'),
    tariffWithTaxesBrlKwh: nullableString(value, 'tariff_with_taxes_brl_kwh'),
    tariffWithoutTaxesBrlKwh: nullableString(value, 'tariff_without_taxes_brl_kwh'),
    wireBTariffBrlKwh: nullableString(value, 'wire_b_tariff_brl_kwh'),
    status: status as BillStatus,
  }
}

export function parsePendingBills(payload: unknown): PendingBills {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const items = payload.items
  if (!Array.isArray(items)) throw new Error('Resposta inválida da API: items')
  return { count: requireNumber(payload, 'count'), items: items.map(parseBill) }
}

// Resposta de `/intake-pdf`, `/confirm` e `/reject`: `{status, bill, ...}`.
export function parseBillEnvelope(payload: unknown): UtilityBill {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  return parseBill(payload.bill)
}
