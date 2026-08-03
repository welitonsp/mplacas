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

// `Decimal` do backend chega serializado como string (ver
// `photovoltaic/serialization.py`) — mantido como string aqui e convertido só na
// hora de calcular, igual ao resto do dashboard (`MetricValue`/`toNumber`).
export interface PhotovoltaicPerformanceLatest {
  dc_capacity_kwp: string | null
}

export interface PhotovoltaicBaselineLatest {
  baseline_median_performance_ratio: string | null
  clear_sky_poa_p90_kwh_m2: string | null
}

export interface PhotovoltaicSummaryResponse {
  plant_id: string
  performance: PhotovoltaicPerformanceLatest | null
  baseline: PhotovoltaicBaselineLatest | null
  baseline_unavailable_reason: BaselineUnavailableReason | null
  reference_complete_on: string | null
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

function parsePerformanceLatest(value: unknown): PhotovoltaicPerformanceLatest {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: performance')
  return { dc_capacity_kwp: nullableString(value, 'dc_capacity_kwp') }
}

function parseBaselineLatest(value: unknown): PhotovoltaicBaselineLatest {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: baseline')
  return {
    baseline_median_performance_ratio: nullableString(value, 'baseline_median_performance_ratio'),
    clear_sky_poa_p90_kwh_m2: nullableString(value, 'clear_sky_poa_p90_kwh_m2'),
  }
}

function parseBaselineUnavailableReason(value: unknown): BaselineUnavailableReason | null {
  if (typeof value === 'string' && BASELINE_UNAVAILABLE_REASONS.has(value)) {
    return value as BaselineUnavailableReason
  }
  return null
}

export function parsePhotovoltaicSummary(payload: unknown): PhotovoltaicSummaryResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const performance = payload.performance
  const baseline = payload.baseline
  return {
    plant_id: requireString(payload, 'plant_id'),
    performance: performance === null || performance === undefined ? null : parsePerformanceLatest(performance),
    baseline: baseline === null || baseline === undefined ? null : parseBaselineLatest(baseline),
    baseline_unavailable_reason: parseBaselineUnavailableReason(payload.baseline_unavailable_reason),
    reference_complete_on: nullableString(payload, 'reference_complete_on'),
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
