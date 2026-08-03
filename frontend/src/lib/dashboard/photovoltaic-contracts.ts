// Parser e derivação de "produção esperada" a partir de `GET /photovoltaic/summary`
// (ver ADR-065). Arquivo separado de `contracts.ts` porque esse endpoint pertence a
// um domínio diferente (modelagem técnica fotovoltaica) e carrega um vocabulário
// próprio de motivo de indisponibilidade que não se mistura com os contratos de
// `/energy/*` já existentes.
import { toNumber } from '../format'

// Os três motivos derivados pelo backend quando ainda não existe um baseline
// sazonal defensável (ADR-065, seção 6). `performance_unavailable_reason` e
// `losses_unavailable_reason` usam outro vocabulário (ex: `NO_PERFORMANCE_RESULTS`,
// `NO_LOSS_ASSESSMENTS`) que esta tela não consome — não validamos esses campos.
export type BaselineUnavailableReason =
  | 'NO_PERFORMANCE_HISTORY'
  | 'REFERENCE_YEAR_INCOMPLETE'
  | 'INSUFFICIENT_SEASONAL_SAMPLES'

const BASELINE_UNAVAILABLE_REASONS: ReadonlySet<string> = new Set([
  'NO_PERFORMANCE_HISTORY',
  'REFERENCE_YEAR_INCOMPLETE',
  'INSUFFICIENT_SEASONAL_SAMPLES',
])

// Motivo derivado quando `performance` vem `null` em `/photovoltaic/summary`
// (`read_service.py::PERFORMANCE_UNAVAILABLE_REASON`) — hoje só existe um
// valor, mas o tipo fica pronto para o backend adicionar outros sem quebrar
// o parser (valores desconhecidos viram `null`, nunca lançam exceção).
export type PerformanceUnavailableReason = 'NO_PERFORMANCE_RESULTS'

const PERFORMANCE_UNAVAILABLE_REASONS: ReadonlySet<string> = new Set(['NO_PERFORMANCE_RESULTS'])

// Motivo derivado quando `losses` vem `null` (`read_service.py::LOSSES_UNAVAILABLE_REASON`).
export type LossesUnavailableReason = 'NO_LOSS_ASSESSMENTS'

const LOSSES_UNAVAILABLE_REASONS: ReadonlySet<string> = new Set(['NO_LOSS_ASSESSMENTS'])

// As oito categorias da taxonomia de perdas, na ordem fixa devolvida pelo
// backend (`loss_taxonomy.py::LossCategory`, ecoada por
// `read_service.py::get_latest_losses` e documentada em ADR-065 seção 4) —
// a UI não deve reordenar por severidade.
export type LossCategory =
  | 'COMMUNICATION'
  | 'UNAVAILABILITY'
  | 'CLIPPING'
  | 'SOILING'
  | 'SHADING'
  | 'TEMPERATURE'
  | 'DEGRADATION'
  | 'UNEXPLAINED'

export const LOSS_CATEGORY_ORDER: readonly LossCategory[] = [
  'COMMUNICATION',
  'UNAVAILABILITY',
  'CLIPPING',
  'SOILING',
  'SHADING',
  'TEMPERATURE',
  'DEGRADATION',
  'UNEXPLAINED',
]

// Nível de evidência por trás de `estimated_loss_percent`
// (`loss_taxonomy.py::EvidenceLevel`) — sempre exibido junto do número para
// não apresentar um proxy (ex.: COMMUNICATION) como perda de energia medida
// (ver ADR-065 seção 3).
export type EvidenceLevel = 'LIKELY' | 'POSSIBLE' | 'NOT_DETECTED' | 'NOT_ASSESSABLE'

// `Decimal` do backend chega serializado como string (ver
// `photovoltaic/serialization.py`) — mantido como string aqui e convertido só na
// hora de calcular, igual ao resto do dashboard (`MetricValue`/`toNumber`).
export interface PhotovoltaicPerformanceLatest {
  dc_capacity_kwp: string | null
  performance_ratio: string | null
  temperature_corrected_performance_ratio: string | null
  final_yield_kwh_per_kwp: string | null
  reporting_availability_ratio: string | null
}

export interface PhotovoltaicBaselineLatest {
  baseline_median_performance_ratio: string | null
  clear_sky_poa_p90_kwh_m2: string | null
  degradation_percent: string | null
  annualized_degradation_percent: string | null
  degradation_status: string | null
}

export interface PhotovoltaicLossItem {
  category: LossCategory
  evidence_level: EvidenceLevel
  estimated_loss_percent: string | null
  evidence_codes: string[]
  limitation: string | null
}

export interface PhotovoltaicSummaryResponse {
  plant_id: string
  performance: PhotovoltaicPerformanceLatest | null
  performance_unavailable_reason: PerformanceUnavailableReason | null
  baseline: PhotovoltaicBaselineLatest | null
  baseline_unavailable_reason: BaselineUnavailableReason | null
  reference_complete_on: string | null
  losses: PhotovoltaicLossItem[] | null
  losses_unavailable_reason: LossesUnavailableReason | null
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

function nullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null) return null
  if (typeof value === 'string') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

// Igual a `nullableString`, mas tolera a chave ausente (`undefined`) além de
// `null` — usado nos campos técnicos novos desta etapa para não quebrar
// payloads de teste/produção que ainda não emitem todos os campos opcionais.
// O contrato do backend garante que campos nullable nunca são omitidos
// (ADR-065 seção 3), mas o parser permanece defensivo mesmo assim.
function optionalString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === undefined || value === null) return null
  if (typeof value === 'string') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function parsePerformanceLatest(value: unknown): PhotovoltaicPerformanceLatest {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: performance')
  return {
    dc_capacity_kwp: nullableString(value, 'dc_capacity_kwp'),
    performance_ratio: optionalString(value, 'performance_ratio'),
    temperature_corrected_performance_ratio: optionalString(
      value,
      'temperature_corrected_performance_ratio'
    ),
    final_yield_kwh_per_kwp: optionalString(value, 'final_yield_kwh_per_kwp'),
    reporting_availability_ratio: optionalString(value, 'reporting_availability_ratio'),
  }
}

function parseBaselineLatest(value: unknown): PhotovoltaicBaselineLatest {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: baseline')
  return {
    baseline_median_performance_ratio: nullableString(value, 'baseline_median_performance_ratio'),
    clear_sky_poa_p90_kwh_m2: nullableString(value, 'clear_sky_poa_p90_kwh_m2'),
    degradation_percent: optionalString(value, 'degradation_percent'),
    annualized_degradation_percent: optionalString(value, 'annualized_degradation_percent'),
    degradation_status: optionalString(value, 'degradation_status'),
  }
}

function parseBaselineUnavailableReason(value: unknown): BaselineUnavailableReason | null {
  if (typeof value === 'string' && BASELINE_UNAVAILABLE_REASONS.has(value)) {
    return value as BaselineUnavailableReason
  }
  return null
}

function parsePerformanceUnavailableReason(value: unknown): PerformanceUnavailableReason | null {
  if (typeof value === 'string' && PERFORMANCE_UNAVAILABLE_REASONS.has(value)) {
    return value as PerformanceUnavailableReason
  }
  return null
}

function parseLossesUnavailableReason(value: unknown): LossesUnavailableReason | null {
  if (typeof value === 'string' && LOSSES_UNAVAILABLE_REASONS.has(value)) {
    return value as LossesUnavailableReason
  }
  return null
}

function isLossCategory(value: unknown): value is LossCategory {
  return typeof value === 'string' && (LOSS_CATEGORY_ORDER as readonly string[]).includes(value)
}

const EVIDENCE_LEVELS: ReadonlySet<string> = new Set([
  'LIKELY',
  'POSSIBLE',
  'NOT_DETECTED',
  'NOT_ASSESSABLE',
])

function parseLossItem(value: unknown): PhotovoltaicLossItem {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: losses[]')
  const category = value.category
  if (!isLossCategory(category)) throw new Error('Resposta inválida da API: losses[].category')
  const evidenceLevel = value.evidence_level
  if (typeof evidenceLevel !== 'string' || !EVIDENCE_LEVELS.has(evidenceLevel)) {
    throw new Error('Resposta inválida da API: losses[].evidence_level')
  }
  const evidenceCodes = value.evidence_codes
  return {
    category,
    evidence_level: evidenceLevel as EvidenceLevel,
    estimated_loss_percent: optionalString(value, 'estimated_loss_percent'),
    evidence_codes:
      Array.isArray(evidenceCodes) && evidenceCodes.every((code) => typeof code === 'string')
        ? evidenceCodes
        : [],
    limitation: optionalString(value, 'limitation'),
  }
}

function parseLosses(value: unknown): PhotovoltaicLossItem[] {
  if (!Array.isArray(value)) throw new Error('Resposta inválida da API: losses')
  return value.map(parseLossItem)
}

export function parsePhotovoltaicSummary(payload: unknown): PhotovoltaicSummaryResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const performance = payload.performance
  const baseline = payload.baseline
  const losses = payload.losses
  return {
    plant_id: requireString(payload, 'plant_id'),
    performance: performance === null || performance === undefined ? null : parsePerformanceLatest(performance),
    performance_unavailable_reason: parsePerformanceUnavailableReason(
      payload.performance_unavailable_reason
    ),
    baseline: baseline === null || baseline === undefined ? null : parseBaselineLatest(baseline),
    baseline_unavailable_reason: parseBaselineUnavailableReason(payload.baseline_unavailable_reason),
    reference_complete_on: nullableString(payload, 'reference_complete_on'),
    losses: losses === null || losses === undefined ? null : parseLosses(losses),
    losses_unavailable_reason: parseLossesUnavailableReason(payload.losses_unavailable_reason),
  }
}

// Produção diária esperada (kWh) para a usina, calculada a partir do baseline
// sazonal já pronto que o backend devolve — nenhuma fórmula é reimplementada
// aqui além da multiplicação final por capacidade instalada (ver ADR-065, seção 4,
// e `photovoltaic/seasonal_baseline.py`): `baseline_median_performance_ratio` é a
// razão de performance robusta da estação, `clear_sky_poa_p90_kwh_m2` é
// numericamente igual às "horas de referência" (irradiância de referência STC =
// 1 kW/m²), então `dc_capacity_kwp × clear_sky_poa_p90_kwh_m2 ×
// baseline_median_performance_ratio` reproduz `final_yield_kwh_per_kwp ×
// dc_capacity_kwp` (`performance.py`) para um dia representativo da estação.
export type ExpectedDailyProduction =
  | { available: true; kwh: number }
  | { available: false; reason: BaselineUnavailableReason; referenceCompleteOn: string | null }

export function deriveExpectedDailyProduction(
  summary: PhotovoltaicSummaryResponse
): ExpectedDailyProduction {
  if (summary.baseline === null || summary.baseline_unavailable_reason !== null) {
    return {
      available: false,
      reason: summary.baseline_unavailable_reason ?? 'NO_PERFORMANCE_HISTORY',
      referenceCompleteOn: summary.reference_complete_on,
    }
  }

  const dcCapacityKwp = toNumber(summary.performance?.dc_capacity_kwp ?? null)
  const clearSkyPoaKwhM2 = toNumber(summary.baseline.clear_sky_poa_p90_kwh_m2)
  const performanceRatio = toNumber(summary.baseline.baseline_median_performance_ratio)

  // Defensivo: um `SeasonalPvBaselineRecord` só existe quando já houve performance
  // elegível persistida, e essa nunca é calculada sem `dc_capacity_kwp` conhecida
  // (`performance_service.py`) — este ramo não deveria disparar em produção, mas
  // não inventamos um número se algum campo vier nulo mesmo assim.
  if (dcCapacityKwp == null || dcCapacityKwp <= 0 || clearSkyPoaKwhM2 == null || performanceRatio == null) {
    return { available: false, reason: 'NO_PERFORMANCE_HISTORY', referenceCompleteOn: null }
  }

  const kwh = dcCapacityKwp * clearSkyPoaKwhM2 * performanceRatio
  if (!Number.isFinite(kwh) || kwh <= 0) {
    return { available: false, reason: 'NO_PERFORMANCE_HISTORY', referenceCompleteOn: null }
  }

  return { available: true, kwh }
}

function formatIsoDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-')
  if (!year || !month || !day) return isoDate
  return `${day}/${month}/${year}`
}

// Mensagem específica ao motivo, exibida no lugar do percentual de desempenho e
// da linha tracejada de "esperado" quando a produção esperada não está disponível
// — nunca um card vazio silencioso (ver skill frontend-design).
export function baselineUnavailableMessage(
  reason: BaselineUnavailableReason,
  referenceCompleteOn: string | null
): string {
  switch (reason) {
    case 'NO_PERFORMANCE_HISTORY':
      return 'Produção esperada ainda não disponível — histórico de desempenho insuficiente para esta usina.'
    case 'REFERENCE_YEAR_INCOMPLETE':
      return referenceCompleteOn
        ? `Produção esperada disponível a partir de ${formatIsoDate(referenceCompleteOn)} — o primeiro ano de referência da usina ainda está em formação.`
        : 'Produção esperada ainda não disponível — o primeiro ano de referência da usina ainda está em formação.'
    case 'INSUFFICIENT_SEASONAL_SAMPLES':
      return 'Produção esperada ainda não disponível — amostras sazonais insuficientes para esta época do ano.'
  }
}

// Mesmo princípio de `baselineUnavailableMessage`, estendido para os outros
// dois blocos de `/photovoltaic/summary` que também podem vir `null`
// (Etapa 6): a seção correspondente mostra o motivo específico, nunca um
// card técnico vazio sem explicação.
export function performanceUnavailableMessage(_reason: PerformanceUnavailableReason): string {
  return 'Desempenho técnico ainda não disponível — nenhum resultado calculado para esta usina.'
}

export function lossesUnavailableMessage(_reason: LossesUnavailableReason): string {
  return 'Atribuição de causas de perda ainda não disponível — nenhuma avaliação calculada para esta usina.'
}

// `performance_ratio`, `temperature_corrected_performance_ratio` e
// `reporting_availability_ratio` chegam como razão 0–1 (`units_json` do
// backend descreve `performance_ratio`/`availability` como `"ratio"`, ver
// `performance.py::PERFORMANCE_UNITS`) — diferente de `degradation_percent`,
// `annualized_degradation_percent` e `estimated_loss_percent`, que o backend
// já emite em escala percentual (`BASELINE_UNITS`/`LOSS_UNITS` em
// `serialization.py`). Esta função converte só a primeira família para não
// multiplicar por 100 um valor que já está em percentual.
export function ratioToPercent(value: string | null): number | null {
  if (value === null) return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric * 100 : null
}
