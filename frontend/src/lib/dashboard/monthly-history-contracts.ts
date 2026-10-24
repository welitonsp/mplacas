// Parser do contrato de `GET /reports/monthly/history` (histórico de produção
// por ciclo de faturamento, usado pelo gráfico `MonthlyProductionSection`).
// Arquivo separado dos demais parsers de `dashboard/` pelo mesmo motivo de
// `financial-return-contracts.ts`/`photovoltaic-contracts.ts`: vocabulário e
// forma de indisponibilidade próprios (ciclos fechados, sem estado "em
// curso"), que não se misturam com o contrato de `/energy/executive/latest`.
//
// `production_kwh` chega como string (`Decimal` serializado) ou `null` —
// nunca `0` como substituto de ausência (ver skill `chart-standards`) —
// convertido para número só neste parser, porque aqui o valor alimenta
// diretamente `BarList`, que espera `number | null`.

export interface MonthlyProductionCycleQuality {
  missingDays: number | null
  provisionalDays: number | null
  incompleteDays: number | null
  unavailableDays: number | null
  // Dias sem leitura estimados pelo sol (ADR-082); `null` em snapshot antigo.
  estimatedDays?: number | null
}

export type GridInjectionBasis = 'METER' | 'BILL_LINE'

// Conferência da distribuidora (ADR-084), calculada no backend.
export type UtilityCheckVerdict = 'OK' | 'SUSPECT' | 'LOSS' | 'IMPOSSIBLE' | 'UNVERIFIABLE'

export interface UtilityCheck {
  verdict: UtilityCheckVerdict
  missingCreditsKwh: number | null
  creditsAvailableKwh: number | null
  creditsUsedKwh: number | null
  creditBalanceKwh: number | null
  // Números da prova: leitura do medidor e saldo de partida (fatura anterior).
  meterExportKwh: number | null
  previousBalanceKwh: number | null
  exportSharePercent: number | null
  exportShareBaselinePercent: number | null
  reasons: string[]
}

export interface MonthlyProductionCycle {
  referenceMonth: string
  billId: string
  status: string
  // Período exato da fatura (ADR-083, etapa 3); `null` se o backend for
  // anterior ou a fatura não estiver mais confirmada.
  cycleStart: string | null
  cycleEnd: string | null
  // Placas (inversor) no ciclo da fatura.
  productionKwh: number | null
  // Distribuidora, tal como gravado no relatório do ciclo: energia enviada à
  // rede e trazida da rede. `null` em relatório antigo — nunca 0.
  gridInjectionKwh: number | null
  // De onde veio a injeção (ADR-078): `METER` = leitura do medidor da
  // distribuidora; `BILL_LINE` = linha de injeção da fatura, que no layout
  // atual é a energia COMPENSADA, não a medida. `null` (backend anterior ou
  // valor desconhecido) nunca é tratado como medidor.
  gridInjectionBasis: GridInjectionBasis | null
  // Código da distribuidora na fatura (ex.: `EQUATORIAL_GO`).
  distributor: string | null
  importedKwh: number | null
  // Autoconsumo calculado pelo motor (placas − enviado à rede), não pela tela.
  selfConsumptionKwh: number | null
  quality: MonthlyProductionCycleQuality | null
  // `null` em backend anterior ao ADR-084: sem conferência, nunca "OK".
  utilityCheck: UtilityCheck | null
}

export interface MonthlyProductionHistoryResponse {
  plantId: string
  limit: number
  cyclesReturned: number
  cycles: MonthlyProductionCycle[]
}

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

function numberValue(source: Record<string, unknown>, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

// Nunca lança para `null`/`undefined` — `production_kwh` legitimamente vem
// `null` quando o ciclo fechado não tem produção diária suficiente para
// consolidar um total (ver contrato do endpoint). Diferente do resto do
// dashboard, aqui o parser já converte para `number`, porque o consumidor
// (`BarList`) trabalha com `number | null`, não com a string decimal crua.
function nullableDecimalNumber(source: Record<string, unknown>, key: string): number | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string') {
    const numeric = Number(value)
    if (Number.isFinite(numeric)) return numeric
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  throw new Error(`Resposta inválida da API: ${key}`)
}

function nullableIsoDate(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function nullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

// Valor novo no backend vira `null` (sem afirmar origem), não erro de tela.
function gridInjectionBasis(source: Record<string, unknown>): GridInjectionBasis | null {
  const value = nullableString(source, 'grid_injection_basis')
  return value === 'METER' || value === 'BILL_LINE' ? value : null
}

function nullableInt(source: Record<string, unknown>, key: string): number | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'number' && Number.isFinite(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

// O objeto `quality` inteiro pode vir `null` quando o snapshot não tem
// nenhuma das quatro chaves (ver contrato do endpoint) — distinto de um
// objeto presente com os quatro contadores `null` individualmente, mas
// ambos os casos resultam no mesmo estado para quem consome (nenhuma lacuna
// conhecida a reportar).
function parseQuality(value: unknown): MonthlyProductionCycleQuality | null {
  if (value === null || value === undefined) return null
  if (!isRecord(value)) throw new Error('Resposta inválida da API: quality')
  return {
    missingDays: nullableInt(value, 'missing_days'),
    provisionalDays: nullableInt(value, 'provisional_days'),
    incompleteDays: nullableInt(value, 'incomplete_days'),
    unavailableDays: nullableInt(value, 'unavailable_days'),
    estimatedDays: nullableInt(value, 'estimated_production_days'),
  }
}

const VERDICTS: readonly UtilityCheckVerdict[] = ['OK', 'SUSPECT', 'LOSS', 'IMPOSSIBLE', 'UNVERIFIABLE']

// Veredito novo no backend vira "sem conferência", não erro de tela nem "OK".
function parseUtilityCheck(value: unknown): UtilityCheck | null {
  if (value === null || value === undefined) return null
  if (!isRecord(value)) throw new Error('Resposta inválida da API: utility_check')
  const raw = value.verdict
  const verdict = VERDICTS.includes(raw as UtilityCheckVerdict) ? (raw as UtilityCheckVerdict) : 'UNVERIFIABLE'
  const reasons = Array.isArray(value.reasons) ? value.reasons.filter((item): item is string => typeof item === 'string') : []
  return {
    verdict,
    missingCreditsKwh: nullableDecimalNumber(value, 'missing_credits_kwh'),
    creditsAvailableKwh: nullableDecimalNumber(value, 'credits_available_kwh'),
    creditsUsedKwh: nullableDecimalNumber(value, 'credits_used_kwh'),
    creditBalanceKwh: nullableDecimalNumber(value, 'credit_balance_kwh'),
    meterExportKwh: nullableDecimalNumber(value, 'meter_export_kwh'),
    previousBalanceKwh: nullableDecimalNumber(value, 'previous_balance_kwh'),
    exportSharePercent: nullableDecimalNumber(value, 'export_share_percent'),
    exportShareBaselinePercent: nullableDecimalNumber(value, 'export_share_baseline_percent'),
    reasons,
  }
}

function parseCycle(value: unknown): MonthlyProductionCycle {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: cycles[]')
  return {
    referenceMonth: requireString(value, 'reference_month'),
    billId: requireString(value, 'bill_id'),
    status: requireString(value, 'status'),
    cycleStart: nullableIsoDate(value, 'cycle_start'),
    cycleEnd: nullableIsoDate(value, 'cycle_end'),
    productionKwh: nullableDecimalNumber(value, 'production_kwh'),
    gridInjectionKwh: nullableDecimalNumber(value, 'grid_injection_kwh'),
    gridInjectionBasis: gridInjectionBasis(value),
    distributor: nullableString(value, 'distributor'),
    importedKwh: nullableDecimalNumber(value, 'imported_kwh'),
    selfConsumptionKwh: nullableDecimalNumber(value, 'self_consumption_kwh'),
    quality: parseQuality(value.quality),
    utilityCheck: parseUtilityCheck(value.utility_check),
  }
}

export function parseMonthlyProductionHistory(payload: unknown): MonthlyProductionHistoryResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const cycles = payload.cycles
  if (!Array.isArray(cycles)) throw new Error('Resposta inválida da API: cycles')
  return {
    plantId: requireString(payload, 'plant_id'),
    limit: numberValue(payload, 'limit'),
    cyclesReturned: numberValue(payload, 'cycles_returned'),
    cycles: cycles.map(parseCycle),
  }
}
