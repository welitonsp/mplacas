// Parser do "conta ciclo a ciclo" da aba Dinheiro: lê os campos de dinheiro de
// `GET /reports/monthly/history` (fatura e economia estimada de cada ciclo +
// `savings_window`, o total pronto do backend). Arquivo próprio, de propósito:
// `monthly-history-contracts.ts` serve ao gráfico da aba Energia e não muda.
//
// Regras:
// - Valores em reais ficam como TEXTO decimal (como o backend manda); nunca
//   viram número aqui e nenhuma conta é feita no frontend — o total vem só de
//   `savings_window`.
// - Campo novo ausente (API anterior) = "indisponível", nunca 0 e nunca erro.
// - Campo presente com tipo errado = payload inválido (lança).

export type SavingsTariffSource = 'DISTRIBUTOR_FULL_TARIFF' | 'BILL_TARIFF'

export type LedgerGapCause =
  | 'OUTDATED_CALCULATION'
  | 'PARTIAL_PRODUCTION'
  | 'SAVINGS_UNAVAILABLE'
  | 'REPORT_PREDATES_SAVINGS'

// Motivo sintético: a API não trouxe os campos de economia (versão anterior).
export const LEDGER_API_WITHOUT_SAVINGS = 'API_WITHOUT_SAVINGS'

export interface LedgerCycle {
  referenceMonth: string
  billId: string
  billTotalAmountBrl: string | null
  estimatedSavingsBrl: string | null
  // Preenchido sempre que `estimatedSavingsBrl` é `null`.
  savingsUnavailableReason: string | null
  savingsTariffSource: SavingsTariffSource | null
  savingsGapCause: LedgerGapCause | null
  reportCreatedAt: string | null
  isCommissioningMonth: boolean | null
  isBeforeCommissioning: boolean | null
  supersededByRebilling: boolean
}

export interface SavingsWindow {
  totalEstimatedSavingsBrl: string | null
  cyclesInWindow: number
  cyclesWithSavings: number
  cyclesWithoutSavings: number
  cyclesExcludedCommissioning: number
  cyclesSupersededByRebilling: number
  commissioningKnown: boolean
  firstReferenceMonth: string | null
  lastReferenceMonth: string | null
  cyclesWithBillTariff: number
  cyclesWithOutdatedOrPartial: number
}

export interface CycleLedger {
  // Do mais recente ao mais antigo (o backend entrega do mais antigo ao mais novo).
  cycles: LedgerCycle[]
  // `null` = API sem `savings_window`: sem total, nunca "R$ 0,00".
  window: SavingsWindow | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function invalid(key: string): never {
  throw new Error(`Resposta inválida da API: ${key}`)
}

function requireString(source: Record<string, unknown>, key: string): string {
  const value = source[key]
  if (typeof value !== 'string' || value.trim() === '') invalid(key)
  return value
}

function nullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value.trim() === '' ? null : value
  return invalid(key)
}

const DECIMAL = /^-?\d+(\.\d+)?$/

// Decimal em texto, possivelmente negativo. Mantido como texto.
function nullableMoney(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string' && DECIMAL.test(value.trim())) return value.trim()
  return invalid(key)
}

function nullableBoolean(source: Record<string, unknown>, key: string): boolean | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'boolean') return value
  return invalid(key)
}

function requireCount(source: Record<string, unknown>, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isInteger(value) && value >= 0) return value
  return invalid(key)
}

function tariffSource(value: string | null): SavingsTariffSource | null {
  return value === 'DISTRIBUTOR_FULL_TARIFF' || value === 'BILL_TARIFF' ? value : null
}

const GAP_CAUSES: readonly string[] = [
  'OUTDATED_CALCULATION',
  'PARTIAL_PRODUCTION',
  'SAVINGS_UNAVAILABLE',
  'REPORT_PREDATES_SAVINGS',
]

// Causa nova no backend vira `null` (sem selo), não erro de tela.
function gapCause(value: string | null): LedgerGapCause | null {
  return value !== null && GAP_CAUSES.includes(value) ? (value as LedgerGapCause) : null
}

function parseCycle(value: unknown): LedgerCycle {
  if (!isRecord(value)) return invalid('cycles[]')
  const savings = nullableMoney(value, 'estimated_savings_brl')
  let reason = nullableString(value, 'savings_unavailable_reason')
  // Sem valor e sem motivo: ou a API é anterior ao campo (chave ausente) ou o
  // backend não explicou. Nos dois casos, indisponível — nunca zero.
  if (savings === null && reason === null) {
    reason = 'estimated_savings_brl' in value ? 'SAVINGS_UNAVAILABLE' : LEDGER_API_WITHOUT_SAVINGS
  }
  return {
    referenceMonth: requireString(value, 'reference_month'),
    billId: requireString(value, 'bill_id'),
    billTotalAmountBrl: nullableMoney(value, 'bill_total_amount_brl'),
    estimatedSavingsBrl: savings,
    // Com valor presente, motivo antigo/solto não vale.
    savingsUnavailableReason: savings === null ? reason : null,
    savingsTariffSource: tariffSource(nullableString(value, 'savings_tariff_source')),
    savingsGapCause: gapCause(nullableString(value, 'savings_gap_cause')),
    reportCreatedAt: nullableString(value, 'report_created_at'),
    isCommissioningMonth: nullableBoolean(value, 'is_commissioning_month'),
    isBeforeCommissioning: nullableBoolean(value, 'is_before_commissioning'),
    supersededByRebilling: value.superseded_by_rebilling === true,
  }
}

function parseWindow(value: unknown): SavingsWindow | null {
  if (value === null || value === undefined) return null
  if (!isRecord(value)) return invalid('savings_window')
  return {
    totalEstimatedSavingsBrl: nullableMoney(value, 'total_estimated_savings_brl'),
    cyclesInWindow: requireCount(value, 'cycles_in_window'),
    cyclesWithSavings: requireCount(value, 'cycles_with_savings'),
    cyclesWithoutSavings: requireCount(value, 'cycles_without_savings'),
    cyclesExcludedCommissioning: requireCount(value, 'cycles_excluded_commissioning'),
    cyclesSupersededByRebilling: requireCount(value, 'cycles_superseded_by_rebilling'),
    // Só `true` explícito confirma data de ligação; ausente = desconhecida.
    commissioningKnown: value.commissioning_known === true,
    firstReferenceMonth: nullableString(value, 'first_reference_month'),
    lastReferenceMonth: nullableString(value, 'last_reference_month'),
    cyclesWithBillTariff: requireCount(value, 'cycles_with_bill_tariff'),
    cyclesWithOutdatedOrPartial: requireCount(value, 'cycles_with_outdated_or_partial'),
  }
}

export function parseCycleLedger(payload: unknown): CycleLedger {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  if (!Array.isArray(payload.cycles)) return invalid('cycles')
  return {
    // `slice().reverse()` mantém, dentro do mesmo mês, o cálculo mais novo primeiro.
    cycles: payload.cycles.map(parseCycle).reverse(),
    window: parseWindow(payload.savings_window),
  }
}
