export type MetricValue = string | number | null
export type Severity = 'success' | 'warning' | 'danger' | 'neutral'

export interface CycleQuality {
  missing_days: number
  provisional_days: number
  incomplete_days: number
  unavailable_days: number
}

export interface ExecutiveIndicators {
  cycle_production_kwh: MetricValue
  imported_kwh: MetricValue
  injected_kwh: MetricValue
  estimated_self_consumption_kwh: MetricValue
  estimated_total_consumption_kwh: MetricValue
  self_consumption_rate_percent: MetricValue
  self_sufficiency_rate_percent: MetricValue
  grid_dependency_rate_percent: MetricValue
  exported_generation_rate_percent: MetricValue
  credit_coverage_rate_percent: MetricValue
  bill_energy_component_brl: MetricValue
  health_score: MetricValue
}

export interface ExecutiveCycle {
  reference_month: string
  quality: CycleQuality
  indicators: ExecutiveIndicators
}

export type TrendDirection = 'UP' | 'DOWN' | 'STABLE'

export interface TrendMetric {
  absolute_delta: MetricValue
  percent_delta: MetricValue
  direction: TrendDirection
}

export interface TrendMetrics {
  production: TrendMetric
  total_consumption: TrendMetric
  imported_energy: TrendMetric
  self_sufficiency_delta_points: MetricValue
  health_score_delta: MetricValue
}

export interface ExecutiveTrend {
  current_reference_month: string
  previous_reference_month: string
  metrics: TrendMetrics
}

export interface ExecutiveDashboardResponse {
  plant_id: string
  status: string
  headline: string
  priority_actions: string[]
  current_cycle: ExecutiveCycle
  trend: ExecutiveTrend | null
}

// Vocabulário compartilhado com o backend (ver intelligence/anomaly_engine.py::AnomalyLevel).
export type AnomalyLevel = 'NORMAL' | 'ATTENTION' | 'ANOMALY' | 'CRITICAL'
export const ANOMALY_LEVELS: ReadonlySet<string> = new Set(['NORMAL', 'ATTENTION', 'ANOMALY', 'CRITICAL'])

export interface AnomalyDailyPoint {
  date: string
  actual_production_kwh: MetricValue
  expected_production_kwh: MetricValue
  level: AnomalyLevel
  deviation_percent: MetricValue
  // Preenchido só quando a usina tem coordenadas configuradas (coleta Open-Meteo
  // ativa). Em qualquer organização nova vem `null` — todo consumidor deste campo
  // precisa tratar ausência sem quebrar (ver YieldCard e overlay de irradiância).
  irradiation_kwh_m2: MetricValue
}

export interface AnomalyDashboardResponse {
  plant_id: string
  days_analyzed: number
  current_streak_days: number
  worst_level: AnomalyLevel
  daily: AnomalyDailyPoint[]
}

export interface FetchState {
  data: ExecutiveDashboardResponse | null
  loading: boolean
  error: string | null
  lastUpdated: Date | null
}

// `NOT_FOUND` = ainda não há dado diário coletado para o período pedido (404 —
// não é uma falha do sistema, é um estado esperado para usina nova/sem backfill).
// `SERVER_ERROR` = 5xx ou falha de rede — aí sim algo quebrou e vale oferecer retry.
export type AnomalyFetchError = 'NOT_FOUND' | 'SERVER_ERROR'

export interface AnomalyFetchState {
  data: AnomalyDashboardResponse | null
  loading: boolean
  error: AnomalyFetchError | null
}

// Classifica o status HTTP de `/energy/anomalies/latest` em uma mensagem de estado
// distinta — nunca trata 404 (sem dado ainda) e 5xx/rede (algo quebrou) como a
// mesma coisa. 401 retorna `null` porque `apiFetch` já tentou refresh e, se ainda
// assim falhou, o usuário está sendo deslogado (não é um estado a comunicar aqui).
export function classifyAnomalyErrorStatus(status: number): AnomalyFetchError | null {
  if (status === 401) return null
  if (status === 404) return 'NOT_FOUND'
  return 'SERVER_ERROR'
}

// Data (ISO `YYYY-MM-DD`) do último dia com produção diária realmente coletada
// (`actual_production_kwh` não nulo) no payload de anomalias — usado para mostrar
// o frescor real do dado em vez da hora em que o navegador fez o fetch. `daily`
// vem em ordem cronológica ascendente (ver `intelligence/anomaly_service.py`).
export function latestNonNullProductionDate(daily: readonly AnomalyDailyPoint[]): string | null {
  for (let i = daily.length - 1; i >= 0; i -= 1) {
    if (daily[i].actual_production_kwh != null) return daily[i].date
  }
  return null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireRecord(source: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = source[key]
  if (!isRecord(value)) throw new Error(`Resposta inválida da API: ${key}`)
  return value
}

function requireString(source: Record<string, unknown>, key: string): string {
  const value = source[key]
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value
}

function metricValue(source: Record<string, unknown>, key: string): MetricValue {
  const value = source[key]
  if (value === null || typeof value === 'string' || typeof value === 'number') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function numberValue(source: Record<string, unknown>, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

const TREND_DIRECTIONS: ReadonlySet<string> = new Set(['UP', 'DOWN', 'STABLE'])

function requireDirection(source: Record<string, unknown>, key: string): TrendDirection {
  const value = source[key]
  if (typeof value !== 'string' || !TREND_DIRECTIONS.has(value)) {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value as TrendDirection
}

function parseTrendMetric(source: Record<string, unknown>, key: string): TrendMetric {
  const metric = requireRecord(source, key)
  return {
    absolute_delta: metricValue(metric, 'absolute_delta'),
    percent_delta: metricValue(metric, 'percent_delta'),
    direction: requireDirection(metric, 'direction'),
  }
}

function optionalTrend(source: Record<string, unknown>): ExecutiveTrend | null {
  const trend = source.trend
  if (trend === null) return null
  if (!isRecord(trend)) throw new Error('Resposta inválida da API: trend')
  const metrics = requireRecord(trend, 'metrics')
  return {
    current_reference_month: requireString(trend, 'current_reference_month'),
    previous_reference_month: requireString(trend, 'previous_reference_month'),
    metrics: {
      production: parseTrendMetric(metrics, 'production'),
      total_consumption: parseTrendMetric(metrics, 'total_consumption'),
      imported_energy: parseTrendMetric(metrics, 'imported_energy'),
      self_sufficiency_delta_points: metricValue(metrics, 'self_sufficiency_delta_points'),
      health_score_delta: metricValue(metrics, 'health_score_delta'),
    },
  }
}

function requireAnomalyLevel(source: Record<string, unknown>, key: string): AnomalyLevel {
  const value = source[key]
  if (typeof value !== 'string' || !ANOMALY_LEVELS.has(value)) {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value as AnomalyLevel
}

export function parseAnomalyDaily(value: unknown): AnomalyDailyPoint {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: daily')
  return {
    date: requireString(value, 'date'),
    actual_production_kwh: metricValue(value, 'actual_production_kwh'),
    expected_production_kwh: metricValue(value, 'expected_production_kwh'),
    level: requireAnomalyLevel(value, 'level'),
    deviation_percent: metricValue(value, 'deviation_percent'),
    irradiation_kwh_m2: metricValue(value, 'irradiation_kwh_m2'),
  }
}

export function parseAnomalyDashboard(payload: unknown): AnomalyDashboardResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const daily = payload.daily
  if (!Array.isArray(daily)) throw new Error('Resposta inválida da API: daily')
  return {
    plant_id: requireString(payload, 'plant_id'),
    days_analyzed: numberValue(payload, 'days_analyzed'),
    current_streak_days: numberValue(payload, 'current_streak_days'),
    worst_level: requireAnomalyLevel(payload, 'worst_level'),
    daily: daily.map(parseAnomalyDaily),
  }
}

export function parseExecutiveDashboard(payload: unknown): ExecutiveDashboardResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')

  const currentCycle = requireRecord(payload, 'current_cycle')
  const quality = requireRecord(currentCycle, 'quality')
  const indicators = requireRecord(currentCycle, 'indicators')
  const priorityActions = payload.priority_actions

  if (!Array.isArray(priorityActions) || !priorityActions.every((item) => typeof item === 'string')) {
    throw new Error('Resposta inválida da API: priority_actions')
  }

  return {
    plant_id: requireString(payload, 'plant_id'),
    status: requireString(payload, 'status'),
    headline: requireString(payload, 'headline'),
    priority_actions: priorityActions,
    current_cycle: {
      reference_month: requireString(currentCycle, 'reference_month'),
      quality: {
        missing_days: numberValue(quality, 'missing_days'),
        provisional_days: numberValue(quality, 'provisional_days'),
        incomplete_days: numberValue(quality, 'incomplete_days'),
        unavailable_days: numberValue(quality, 'unavailable_days'),
      },
      indicators: {
        cycle_production_kwh: metricValue(indicators, 'cycle_production_kwh'),
        imported_kwh: metricValue(indicators, 'imported_kwh'),
        injected_kwh: metricValue(indicators, 'injected_kwh'),
        estimated_self_consumption_kwh: metricValue(indicators, 'estimated_self_consumption_kwh'),
        estimated_total_consumption_kwh: metricValue(indicators, 'estimated_total_consumption_kwh'),
        self_consumption_rate_percent: metricValue(indicators, 'self_consumption_rate_percent'),
        self_sufficiency_rate_percent: metricValue(indicators, 'self_sufficiency_rate_percent'),
        grid_dependency_rate_percent: metricValue(indicators, 'grid_dependency_rate_percent'),
        exported_generation_rate_percent: metricValue(indicators, 'exported_generation_rate_percent'),
        credit_coverage_rate_percent: metricValue(indicators, 'credit_coverage_rate_percent'),
        bill_energy_component_brl: metricValue(indicators, 'bill_energy_component_brl'),
        health_score: metricValue(indicators, 'health_score'),
      },
    },
    trend: optionalTrend(payload),
  }
}
