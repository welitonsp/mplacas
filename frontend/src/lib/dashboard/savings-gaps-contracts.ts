// Contrato de `/reports/monthly/savings-gaps` e `.../reprocess` (ADR-081):
// faturas confirmadas cuja economia ficou de fora da soma do retorno do
// investimento, ou foi calculada pela fórmula antiga. Valores em R$ chegam
// como string (Decimal serializado) e só viram número na hora de exibir.

export type SavingsGapCause =
  | 'REPORT_MISSING'
  | 'REPORT_PREDATES_SAVINGS'
  | 'SAVINGS_UNAVAILABLE'
  | 'OUTDATED_CALCULATION'

export interface SavingsGap {
  billId: string
  referenceMonth: string
  cause: SavingsGapCause
  savingsUnavailableReason: string | null
  previousSavingsBrl: string | null
}

export interface ReprocessResult {
  billId: string
  referenceMonth: string
  previousCause: SavingsGapCause
  previousSavingsBrl: string | null
  outcome: 'RECALCULATED' | 'STILL_UNAVAILABLE'
  estimatedSavingsBrl: string | null
  savingsUnavailableReason: string | null
  storedRevision: number | null
}

const CAUSES: readonly SavingsGapCause[] = [
  'REPORT_MISSING',
  'REPORT_PREDATES_SAVINGS',
  'SAVINGS_UNAVAILABLE',
  'OUTDATED_CALCULATION',
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function text(source: Record<string, unknown>, key: string): string {
  const value = source[key]
  if (typeof value === 'string' && value !== '') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function optionalText(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value === '' ? null : value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function cause(source: Record<string, unknown>, key: string): SavingsGapCause {
  const value = source[key]
  if (typeof value === 'string' && (CAUSES as readonly string[]).includes(value)) {
    return value as SavingsGapCause
  }
  throw new Error(`Resposta inválida da API: ${key}`)
}

function items(payload: unknown): Record<string, unknown>[] {
  if (!isRecord(payload) || !Array.isArray(payload.items) || !payload.items.every(isRecord)) {
    throw new Error('Resposta inválida da API: items')
  }
  return payload.items
}

export function parseSavingsGaps(payload: unknown): SavingsGap[] {
  return items(payload).map((item) => ({
    billId: text(item, 'bill_id'),
    referenceMonth: text(item, 'reference_month'),
    cause: cause(item, 'cause'),
    savingsUnavailableReason: optionalText(item, 'savings_unavailable_reason'),
    previousSavingsBrl: optionalText(item, 'previous_savings_brl'),
  }))
}

export function parseReprocessResults(payload: unknown): ReprocessResult[] {
  return items(payload).map((item) => {
    const outcome = item.outcome
    if (outcome !== 'RECALCULATED' && outcome !== 'STILL_UNAVAILABLE') {
      throw new Error('Resposta inválida da API: outcome')
    }
    const revision = item.stored_revision
    if (revision !== null && (typeof revision !== 'number' || !Number.isInteger(revision))) {
      throw new Error('Resposta inválida da API: stored_revision')
    }
    return {
      billId: text(item, 'bill_id'),
      referenceMonth: text(item, 'reference_month'),
      previousCause: cause(item, 'previous_cause'),
      previousSavingsBrl: optionalText(item, 'previous_savings_brl'),
      outcome,
      estimatedSavingsBrl: optionalText(item, 'estimated_savings_brl'),
      savingsUnavailableReason: optionalText(item, 'savings_unavailable_reason'),
      storedRevision: revision,
    }
  })
}
