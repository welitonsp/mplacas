import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { apiFetch } from '../lib/api'
import { PLANT_ID } from '../env'

type MetricValue = string | number | null
type Severity = 'success' | 'warning' | 'danger' | 'neutral'

interface CycleQuality {
  missing_days: number
  provisional_days: number
  incomplete_days: number
  unavailable_days: number
}

interface ExecutiveIndicators {
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

interface ExecutiveCycle {
  reference_month: string
  quality: CycleQuality
  indicators: ExecutiveIndicators
}

type TrendDirection = 'UP' | 'DOWN' | 'STABLE'

interface TrendMetric {
  absolute_delta: MetricValue
  percent_delta: MetricValue
  direction: TrendDirection
}

interface TrendMetrics {
  production: TrendMetric
  total_consumption: TrendMetric
  imported_energy: TrendMetric
  self_sufficiency_delta_points: MetricValue
  health_score_delta: MetricValue
}

interface ExecutiveTrend {
  current_reference_month: string
  previous_reference_month: string
  metrics: TrendMetrics
}

interface ExecutiveDashboardResponse {
  plant_id: string
  status: string
  headline: string
  priority_actions: string[]
  current_cycle: ExecutiveCycle
  trend: ExecutiveTrend | null
}

// Vocabulário compartilhado com o backend (ver intelligence/anomaly_engine.py::AnomalyLevel).
type AnomalyLevel = 'NORMAL' | 'ATTENTION' | 'ANOMALY' | 'CRITICAL'
const ANOMALY_LEVELS: ReadonlySet<string> = new Set(['NORMAL', 'ATTENTION', 'ANOMALY', 'CRITICAL'])

interface AnomalyDailyPoint {
  date: string
  actual_production_kwh: MetricValue
  expected_production_kwh: MetricValue
  level: AnomalyLevel
  deviation_percent: MetricValue
}

interface AnomalyDashboardResponse {
  plant_id: string
  days_analyzed: number
  current_streak_days: number
  worst_level: AnomalyLevel
  daily: AnomalyDailyPoint[]
}

interface FetchState {
  data: ExecutiveDashboardResponse | null
  loading: boolean
  error: string | null
  lastUpdated: Date | null
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

function parseAnomalyDaily(value: unknown): AnomalyDailyPoint {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: daily')
  return {
    date: requireString(value, 'date'),
    actual_production_kwh: metricValue(value, 'actual_production_kwh'),
    expected_production_kwh: metricValue(value, 'expected_production_kwh'),
    level: requireAnomalyLevel(value, 'level'),
    deviation_percent: metricValue(value, 'deviation_percent'),
  }
}

function parseAnomalyDashboard(payload: unknown): AnomalyDashboardResponse {
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

function parseExecutiveDashboard(payload: unknown): ExecutiveDashboardResponse {
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

function formatNumber(value: MetricValue, maximumFractionDigits = 2): string {
  if (value == null) return '—'
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  return numeric.toLocaleString('pt-BR', { maximumFractionDigits })
}

function formatCurrency(value: MetricValue): string {
  if (value == null) return '—'
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  return numeric.toLocaleString('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    maximumFractionDigits: 2,
  })
}

function toNumber(value: MetricValue): number | null {
  if (value == null) return null
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function clampPercent(value: number): number {
  return Math.min(Math.max(value, 0), 100)
}

// Produção diária esperada usada como referência para o cálculo de anomalias
// (GET /energy/anomalies/latest). Baseada no orçamento de geração de 562 kWh/mês
// do relatório SolarView desta usina (562/30 ≈ 18,7 kWh/dia) — ainda não é
// configurável por usina na tela; quando o backend expuser esse dado por
// planta, substituir por um valor vindo da API em vez desta constante fixa.
const EXPECTED_DAILY_PRODUCTION_KWH = 18.7

function formatShortDate(isoDate: string): string {
  const [, month, day] = isoDate.split('-')
  if (!month || !day) return isoDate
  return `${day}/${month}`
}

// Status é calculado no backend (ver intelligence/executive_service.py) — o front
// apenas mapeia o mesmo vocabulário para rótulo pt-BR e cor de severidade, sem
// reimplementar os limiares de health_score.
const STATUS_META: Record<string, { label: string; severity: Severity }> = {
  HEALTHY: { label: 'Saudável', severity: 'success' },
  ATTENTION: { label: 'Atenção', severity: 'warning' },
  CRITICAL: { label: 'Crítico', severity: 'danger' },
}

function statusMeta(status: string): { label: string; severity: Severity } {
  return STATUS_META[status] ?? { label: status, severity: 'neutral' }
}

const SEVERITY_TEXT: Record<Severity, string> = {
  success: 'text-[var(--color-success)]',
  warning: 'text-[var(--color-warning)]',
  danger: 'text-[var(--color-danger)]',
  neutral: 'text-gray-600',
}

const SEVERITY_BG: Record<Severity, string> = {
  success: 'bg-[var(--color-success-light)]',
  warning: 'bg-[var(--color-warning-light)]',
  danger: 'bg-[var(--color-danger-light)]',
  neutral: 'bg-gray-100',
}

const SEVERITY_BORDER_L: Record<Severity, string> = {
  success: 'border-l-[var(--color-success)]',
  warning: 'border-l-[var(--color-warning)]',
  danger: 'border-l-[var(--color-danger)]',
  neutral: 'border-l-gray-300',
}

const SEVERITY_BAR: Record<Severity, string> = {
  success: 'bg-[var(--color-success)]',
  warning: 'bg-[var(--color-warning)]',
  danger: 'bg-[var(--color-danger)]',
  neutral: 'bg-gray-400',
}

const SEVERITY_DOT: Record<Severity, string> = {
  success: 'bg-[var(--color-success)]',
  warning: 'bg-[var(--color-warning)]',
  danger: 'bg-[var(--color-danger)]',
  neutral: 'bg-gray-400',
}

const LEVEL_LABEL: Record<AnomalyLevel, string> = {
  NORMAL: 'Normal',
  ATTENTION: 'Atenção',
  ANOMALY: 'Anomalia',
  CRITICAL: 'Crítico',
}

// Mesmos limiares usados em intelligence/energy_engine.py para o desvio do ciclo
// vs. produção esperada: < 70% = PRODUCTION_WELL_BELOW_EXPECTED (CRITICAL/danger),
// < 85% = PRODUCTION_BELOW_EXPECTED (WARNING), >= 85% = dentro do esperado (success).
// Não inventar um limiar novo aqui — reaproveita o mesmo vocabulário do backend.
function performanceSeverity(percent: number): Severity {
  if (percent < 70) return 'danger'
  if (percent < 85) return 'warning'
  return 'success'
}

// NORMAL = produção dentro do esperado (bom). ATTENTION = desvio leve.
// ANOMALY/CRITICAL = desvio relevante — mesma cor de alerta para os dois,
// diferenciados pelo rótulo textual (ver LEVEL_LABEL), sem inventar um quinto tom.
function levelSeverity(level: AnomalyLevel): Severity {
  if (level === 'NORMAL') return 'success'
  if (level === 'ATTENTION') return 'warning'
  return 'danger'
}

type TrendMetricKey = 'production' | 'total_consumption' | 'imported_energy'

// O sentido de "bom"/"ruim" depende da métrica: produção subir é bom, energia
// importada subir é ruim, e consumo total não tem um sentido óbvio de bom/ruim
// (não pintamos essa métrica). Não usar DOWN=vermelho/UP=verde de forma cega.
const GOOD_DIRECTION: Record<TrendMetricKey, TrendDirection | null> = {
  production: 'UP',
  imported_energy: 'DOWN',
  total_consumption: null,
}

function trendSeverity(metricKey: TrendMetricKey, direction: TrendDirection): Severity {
  const good = GOOD_DIRECTION[metricKey]
  if (good === null || direction === 'STABLE') return 'neutral'
  return direction === good ? 'success' : 'danger'
}

const DIRECTION_SYMBOL: Record<TrendDirection, string> = { UP: '▲', DOWN: '▼', STABLE: '▬' }
const DIRECTION_TEXT: Record<TrendDirection, string> = {
  UP: 'aumentou',
  DOWN: 'diminuiu',
  STABLE: 'estável',
}

function SectionTitle({ children }: { children: string }) {
  return <h3 className="mb-3 text-sm font-semibold text-gray-700">{children}</h3>
}

function MetricCard({
  label,
  value,
  unit,
  partial,
  barPercent,
}: {
  label: string
  value: MetricValue
  unit?: string
  partial?: boolean
  barPercent?: number | null
}) {
  return (
    <div
      className={`relative rounded-xl border bg-white p-5 shadow-sm ${
        partial ? 'border-dashed border-gray-300' : 'border-gray-200'
      }`}
    >
      {partial && (
        <span className="absolute right-3 top-3 rounded-full bg-[var(--color-warning-light)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-warning)]">
          Parcial
        </span>
      )}
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">
        {formatNumber(value)}
        {value != null && unit && (
          <span className="ml-1 text-sm font-normal text-gray-500">{unit}</span>
        )}
      </p>
      {barPercent != null && (
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
          <div
            className="h-full rounded-full bg-[var(--color-brand-primary)]"
            style={{ width: `${clampPercent(barPercent)}%` }}
          />
        </div>
      )}
    </div>
  )
}

function CurrencyCard({ label, value }: { label: string; value: MetricValue }) {
  return (
    <div className="rounded-xl border border-[var(--color-brand-primary)]/20 bg-[var(--color-brand-primary-light)] p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">{formatCurrency(value)}</p>
    </div>
  )
}

function ProductionSplitCard({
  selfConsumption,
  injected,
}: {
  selfConsumption: MetricValue
  injected: MetricValue
}) {
  const sc = toNumber(selfConsumption)
  const inj = toNumber(injected)
  const total = (sc ?? 0) + (inj ?? 0)
  const hasData = sc != null && inj != null && total > 0

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Composição da produção
      </p>
      {!hasData ? (
        <p className="mt-4 text-sm text-gray-400">Dados insuficientes para o gráfico.</p>
      ) : (
        <>
          <div className="mt-4 flex h-3 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full bg-[var(--color-brand-primary)]"
              style={{ width: `${((sc as number) / total) * 100}%` }}
            />
            <div className="h-full bg-gray-300" style={{ width: `${((inj as number) / total) * 100}%` }} />
          </div>
          <div className="mt-3 space-y-1.5 text-xs text-gray-600">
            <p className="flex flex-wrap items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--color-brand-primary)]" />
              Autoconsumo:
              <span className="font-medium text-gray-900">{formatNumber(sc)} kWh</span>
              <span className="text-gray-400">
                ({formatNumber(((sc as number) / total) * 100, 0)}%)
              </span>
            </p>
            <p className="flex flex-wrap items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-gray-300" />
              Injetada na rede:
              <span className="font-medium text-gray-900">{formatNumber(inj)} kWh</span>
              <span className="text-gray-400">
                ({formatNumber(((inj as number) / total) * 100, 0)}%)
              </span>
            </p>
          </div>
        </>
      )}
    </div>
  )
}

// Cor "grid" reutilizada em todo o diagrama de fluxo e no donut: mesmo cinza
// (gray-300, hex #d1d5db) já usado em ProductionSplitCard para "injetada na
// rede". Autoconsumo = brand-primary em todos os pontos. Composição não é
// severidade (bom/ruim) — por isso não usamos success/warning/danger aqui,
// ver skill dataviz.
const GRID_HEX = '#d1d5db'

function EnergyFlowDiagram({
  production,
  selfConsumption,
  injected,
  imported,
  consumption,
}: {
  production: MetricValue
  selfConsumption: MetricValue
  injected: MetricValue
  imported: MetricValue
  consumption: MetricValue
}) {
  const prod = toNumber(production)
  const sc = toNumber(selfConsumption)
  const inj = toNumber(injected)
  const imp = toNumber(imported)
  const cons = toNumber(consumption)

  const hasData = prod != null && prod > 0 && cons != null && cons > 0 && sc != null && inj != null && imp != null

  if (!hasData) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Fluxo de energia no ciclo
        </p>
        <p className="mt-4 text-sm text-gray-400">Dados insuficientes para o diagrama.</p>
      </div>
    )
  }

  const production_ = prod as number
  const consumption_ = cons as number
  const selfConsumption_ = sc as number
  const injected_ = inj as number
  const imported_ = imp as number

  const prodAutoPercent = (selfConsumption_ / production_) * 100
  const prodExportPercent = (injected_ / production_) * 100
  const consAutoPercent = (selfConsumption_ / consumption_) * 100
  const consImportPercent = (imported_ / consumption_) * 100

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Fluxo de energia no ciclo
      </p>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto_1fr] sm:grid-rows-2 sm:items-center sm:gap-x-6 sm:gap-y-3">
        {/* Nó: Produção */}
        <div className="sm:col-start-1 sm:row-start-1 sm:row-span-2 rounded-lg border border-gray-100 bg-gray-50 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">Produção</p>
          <p className="mt-1 text-xl font-semibold text-gray-900">{formatNumber(production_)} kWh</p>
          <div className="mt-3 flex h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full bg-[var(--color-brand-primary)]"
              style={{ width: `${clampPercent(prodAutoPercent)}%` }}
            />
            <div className="h-full bg-gray-300" style={{ width: `${clampPercent(prodExportPercent)}%` }} />
          </div>
          <ul className="mt-2 space-y-1 text-xs text-gray-600">
            <li className="flex items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--color-brand-primary)]" />
              Autoconsumo: <span className="font-medium text-gray-900">{formatNumber(selfConsumption_)} kWh</span>
            </li>
            <li className="flex items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-gray-300" />
              Exportada: <span className="font-medium text-gray-900">{formatNumber(injected_)} kWh</span>
            </li>
          </ul>
        </div>

        {/* Seta: autoconsumo direto (produção → consumo) */}
        <div className="flex items-center justify-center gap-2 text-center sm:col-start-2 sm:row-start-1">
          <span aria-hidden="true" className="text-lg text-[var(--color-brand-primary)] sm:hidden">
            ↓
          </span>
          <span aria-hidden="true" className="hidden text-lg text-[var(--color-brand-primary)] sm:inline">
            →
          </span>
          <span className="text-xs text-gray-500">
            autoconsumo
            <br />
            <span className="font-medium text-gray-900">{formatNumber(selfConsumption_)} kWh</span>
          </span>
        </div>

        {/* Nó: Rede (exportada entra, importada sai) */}
        <div className="rounded-lg border border-dashed border-gray-200 bg-white p-3 text-center sm:col-start-2 sm:row-start-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Rede</p>
          <p className="mt-1 text-xs text-gray-600">
            <span aria-hidden="true">←</span> Exportada: <span className="font-medium text-gray-900">{formatNumber(injected_)} kWh</span>
          </p>
          <p className="mt-0.5 text-xs text-gray-600">
            Importada: <span className="font-medium text-gray-900">{formatNumber(imported_)} kWh</span> <span aria-hidden="true">→</span>
          </p>
        </div>

        {/* Nó: Consumo */}
        <div className="sm:col-start-3 sm:row-start-1 sm:row-span-2 rounded-lg border border-gray-100 bg-gray-50 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">Consumo</p>
          <p className="mt-1 text-xl font-semibold text-gray-900">{formatNumber(consumption_)} kWh</p>
          <div className="mt-3 flex h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full bg-[var(--color-brand-primary)]"
              style={{ width: `${clampPercent(consAutoPercent)}%` }}
            />
            <div className="h-full bg-gray-300" style={{ width: `${clampPercent(consImportPercent)}%` }} />
          </div>
          <ul className="mt-2 space-y-1 text-xs text-gray-600">
            <li className="flex items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--color-brand-primary)]" />
              Autoconsumo: <span className="font-medium text-gray-900">{formatNumber(selfConsumption_)} kWh</span>
            </li>
            <li className="flex items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-gray-300" />
              Importada: <span className="font-medium text-gray-900">{formatNumber(imported_)} kWh</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  )
}

const DONUT_RADIUS = 46
const DONUT_CIRCUMFERENCE = 2 * Math.PI * DONUT_RADIUS

function ConsumptionDonut({
  imported,
  selfConsumption,
}: {
  imported: MetricValue
  selfConsumption: MetricValue
}) {
  const imp = toNumber(imported)
  const sc = toNumber(selfConsumption)
  const total = (imp ?? 0) + (sc ?? 0)
  const hasData = imp != null && sc != null && total > 0

  if (!hasData) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Origem do consumo
        </p>
        <p className="mt-4 text-sm text-gray-400">Dados insuficientes para o gráfico.</p>
      </div>
    )
  }

  const imported_ = imp as number
  const selfConsumption_ = sc as number
  const importedPercent = (imported_ / total) * 100
  const selfConsumptionPercent = (selfConsumption_ / total) * 100

  const selfConsumptionLength = (selfConsumptionPercent / 100) * DONUT_CIRCUMFERENCE
  const importedLength = (importedPercent / 100) * DONUT_CIRCUMFERENCE

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Origem do consumo
      </p>

      <div className="mt-4 flex flex-col items-center gap-4 sm:flex-row sm:items-center">
        <svg
          viewBox="0 0 120 120"
          className="h-32 w-32 shrink-0"
          role="img"
          aria-label={`Origem do consumo: ${formatNumber(selfConsumption_)} kWh de autoconsumo (${formatNumber(
            selfConsumptionPercent,
            0
          )}%) e ${formatNumber(imported_)} kWh importados da concessionária (${formatNumber(
            importedPercent,
            0
          )}%), total de ${formatNumber(total)} kWh.`}
        >
          <circle cx="60" cy="60" r={DONUT_RADIUS} fill="none" stroke="#f3f4f6" strokeWidth="16" />
          <circle
            cx="60"
            cy="60"
            r={DONUT_RADIUS}
            fill="none"
            stroke="var(--color-brand-primary)"
            strokeWidth="16"
            strokeDasharray={`${selfConsumptionLength} ${DONUT_CIRCUMFERENCE}`}
            strokeDashoffset="0"
            transform="rotate(-90 60 60)"
          />
          <circle
            cx="60"
            cy="60"
            r={DONUT_RADIUS}
            fill="none"
            stroke={GRID_HEX}
            strokeWidth="16"
            strokeDasharray={`${importedLength} ${DONUT_CIRCUMFERENCE}`}
            strokeDashoffset={-selfConsumptionLength}
            transform="rotate(-90 60 60)"
          />
          <text
            x="60"
            y="56"
            textAnchor="middle"
            className="fill-gray-900 text-[16px] font-semibold"
          >
            {formatNumber(total, 0)}
          </text>
          <text x="60" y="72" textAnchor="middle" className="fill-gray-400 text-[10px]">
            kWh
          </text>
        </svg>

        {/* Alternativa textual acessível ao SVG — não depende só da cor/gráfico. */}
        <ul className="w-full space-y-2 text-sm text-gray-600">
          <li className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-[var(--color-brand-primary)]" />
            <span className="flex-1">Autoconsumo</span>
            <span className="font-medium text-gray-900">{formatNumber(selfConsumption_)} kWh</span>
            <span className="text-xs text-gray-400">({formatNumber(selfConsumptionPercent, 0)}%)</span>
          </li>
          <li className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-gray-300" />
            <span className="flex-1">Importada da concessionária</span>
            <span className="font-medium text-gray-900">{formatNumber(imported_)} kWh</span>
            <span className="text-xs text-gray-400">({formatNumber(importedPercent, 0)}%)</span>
          </li>
        </ul>
      </div>
    </div>
  )
}

function HeroCard({
  referenceMonth,
  headline,
  status,
  healthScore,
}: {
  referenceMonth: string
  headline: string
  status: string
  healthScore: MetricValue
}) {
  const meta = statusMeta(status)
  const score = toNumber(healthScore)

  return (
    <div
      className={`rounded-xl border border-gray-200 border-l-4 ${SEVERITY_BORDER_L[meta.severity]} bg-white p-5 shadow-sm sm:p-6`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Ciclo de referência: {referenceMonth}
          </p>
          <p className="mt-1 text-xl font-semibold text-gray-900">{headline}</p>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 self-start rounded-full px-3 py-1 text-xs font-semibold ${SEVERITY_BG[meta.severity]} ${SEVERITY_TEXT[meta.severity]}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${SEVERITY_DOT[meta.severity]}`} />
          {meta.label}
        </span>
      </div>

      {score != null && (
        <div className="mt-5">
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span className="font-medium uppercase tracking-wide">Saúde da usina</span>
            <span className={`font-semibold ${SEVERITY_TEXT[meta.severity]}`}>
              {formatNumber(score, 0)}/100
            </span>
          </div>
          <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className={`h-full rounded-full ${SEVERITY_BAR[meta.severity]}`}
              style={{ width: `${clampPercent(score)}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

function QualityBanner({ quality }: { quality: CycleQuality }) {
  const items = [
    { key: 'missing', label: 'ausente', value: quality.missing_days },
    { key: 'provisional', label: 'provisório', value: quality.provisional_days },
    { key: 'incomplete', label: 'incompleto', value: quality.incomplete_days },
    { key: 'unavailable', label: 'indisponível', value: quality.unavailable_days },
  ].filter((item) => item.value > 0)

  if (items.length === 0) {
    return (
      <p className="mt-4 flex items-center gap-1.5 text-xs text-[var(--color-success)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
        Dados consolidados — nenhuma pendência neste ciclo.
      </p>
    )
  }

  return (
    <div className="mt-4 rounded-xl border border-dashed border-[var(--color-warning)] bg-[var(--color-warning-light)] p-4">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-warning)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-warning)]" />
        Dados parciais neste ciclo
      </p>
      <p className="mt-1.5 text-sm text-gray-700">
        {items
          .map((item) => `${item.value} dia${item.value > 1 ? 's' : ''} ${item.label}${item.value > 1 ? 's' : ''}`)
          .join(', ')}
        .
      </p>
    </div>
  )
}

function TrendMetricItem({
  label,
  metric,
  metricKey,
  unit,
}: {
  label: string
  metric: TrendMetric
  metricKey: TrendMetricKey
  unit: string
}) {
  const severity = trendSeverity(metricKey, metric.direction)
  const absolute = toNumber(metric.absolute_delta)
  const percent = toNumber(metric.percent_delta)
  const sign = absolute != null && absolute > 0 ? '+' : ''

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2.5">
      <span className="text-sm text-gray-600">{label}</span>
      <span className={`inline-flex items-center gap-1.5 text-sm font-semibold ${SEVERITY_TEXT[severity]}`}>
        <span aria-hidden="true">{DIRECTION_SYMBOL[metric.direction]}</span>
        <span>
          {sign}
          {formatNumber(absolute)} {unit}
        </span>
        {percent != null && (
          <span className="text-xs font-normal text-gray-400">
            ({percent > 0 ? '+' : ''}
            {formatNumber(percent, 1)}% · {DIRECTION_TEXT[metric.direction]})
          </span>
        )}
      </span>
    </div>
  )
}

function TrendCard({ trend }: { trend: ExecutiveTrend }) {
  const points = toNumber(trend.metrics.self_sufficiency_delta_points)
  const pointsSeverity: Severity = points == null || points === 0 ? 'neutral' : points > 0 ? 'success' : 'danger'

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Comparação com o ciclo anterior
      </p>
      <p className="mt-1 text-xs text-gray-400">
        {trend.previous_reference_month} → {trend.current_reference_month}
      </p>
      <div className="mt-2 divide-y divide-gray-100">
        <TrendMetricItem
          label="Produção"
          metric={trend.metrics.production}
          metricKey="production"
          unit="kWh"
        />
        <TrendMetricItem
          label="Consumo total"
          metric={trend.metrics.total_consumption}
          metricKey="total_consumption"
          unit="kWh"
        />
        <TrendMetricItem
          label="Energia importada"
          metric={trend.metrics.imported_energy}
          metricKey="imported_energy"
          unit="kWh"
        />
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2.5">
          <span className="text-sm text-gray-600">Autossuficiência</span>
          <span className={`text-sm font-semibold ${SEVERITY_TEXT[pointsSeverity]}`}>
            {points != null && points > 0 ? '+' : ''}
            {formatNumber(points, 1)} p.p.
          </span>
        </div>
      </div>
    </div>
  )
}

const ANOMALY_LEGEND: { level: AnomalyLevel; label: string }[] = [
  { level: 'NORMAL', label: 'Normal' },
  { level: 'ATTENTION', label: 'Atenção' },
  { level: 'ANOMALY', label: 'Anomalia/crítico' },
]

function ProductionHistoryChart({
  daily,
  currentStreakDays,
}: {
  daily: AnomalyDailyPoint[]
  currentStreakDays: number
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  if (daily.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Histórico de produção diária
        </p>
        <p className="mt-4 text-sm text-gray-400">
          Ainda não há dados diários suficientes para este gráfico.
        </p>
      </div>
    )
  }

  const maxValue =
    Math.max(
      ...daily.map((d) => {
        const actual = toNumber(d.actual_production_kwh) ?? 0
        const expected = toNumber(d.expected_production_kwh) ?? 0
        return Math.max(actual, expected)
      }),
      1
    ) * 1.1

  // % de desempenho do período: soma do real dividido pela soma do esperado no
  // conjunto de dias exibido — derivado do array `daily` já em mãos, sem cálculo
  // novo no backend (ver instrução da tarefa).
  const totalActual = daily.reduce((sum, d) => sum + (toNumber(d.actual_production_kwh) ?? 0), 0)
  const totalExpected = daily.reduce((sum, d) => sum + (toNumber(d.expected_production_kwh) ?? 0), 0)
  const performancePercent = totalExpected > 0 ? (totalActual / totalExpected) * 100 : null

  const activeDay = activeIndex != null ? daily[activeIndex] : daily[daily.length - 1]
  const activeSeverity = levelSeverity(activeDay.level)

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Histórico de produção diária ({daily.length} dias)
          </p>
          {performancePercent != null && (
            <span
              className={`text-lg font-semibold ${SEVERITY_TEXT[performanceSeverity(performancePercent)]}`}
            >
              Desempenho: {formatNumber(performancePercent, 1)}%
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-gray-500">
          {ANOMALY_LEGEND.map((item) => (
            <span key={item.level} className="inline-flex items-center gap-1">
              <span className={`h-2 w-2 rounded-full ${SEVERITY_DOT[levelSeverity(item.level)]}`} />
              {item.label}
            </span>
          ))}
          <span className="inline-flex items-center gap-1">
            <span className="h-0 w-3 border-t border-dashed border-gray-400" />
            Esperado
          </span>
        </div>
      </div>

      {currentStreakDays > 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-[var(--color-danger)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-danger)]" />
          {currentStreakDays} dia{currentStreakDays > 1 ? 's' : ''} seguido{currentStreakDays > 1 ? 's' : ''} com
          produção abaixo do esperado.
        </p>
      )}

      <div className="mt-4 overflow-x-auto">
        <div
          className="flex items-end gap-[2px]"
          style={{ minWidth: `${daily.length * 8}px`, height: '160px' }}
        >
          {daily.map((d, i) => {
            const actual = toNumber(d.actual_production_kwh) ?? 0
            const expected = toNumber(d.expected_production_kwh) ?? 0
            const barHeightPercent = clampPercent((actual / maxValue) * 100)
            const expectedHeightPercent = clampPercent((expected / maxValue) * 100)
            const severity = levelSeverity(d.level)
            const isActive = activeIndex === i

            return (
              <button
                key={d.date}
                type="button"
                className="relative flex h-full flex-1 items-end rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
                style={{ minWidth: '6px' }}
                onMouseEnter={() => setActiveIndex(i)}
                onFocus={() => setActiveIndex(i)}
                onMouseLeave={() => setActiveIndex(null)}
                onBlur={() => setActiveIndex(null)}
                aria-label={`${formatShortDate(d.date)}: ${formatNumber(actual)} kWh produzidos de ${formatNumber(
                  expected
                )} kWh esperados. Nível: ${LEVEL_LABEL[d.level]}.`}
              >
                <span
                  className="absolute right-0 left-0 border-t border-dashed border-gray-400"
                  style={{ bottom: `${expectedHeightPercent}%` }}
                />
                <span
                  className={`w-full rounded-t-sm ${SEVERITY_BAR[severity]} ${
                    isActive ? '' : 'opacity-90'
                  }`}
                  style={{ height: `${Math.max(barHeightPercent, 2)}%` }}
                />
              </button>
            )
          })}
        </div>
      </div>

      <div className="mt-1 flex justify-between text-[10px] text-gray-400">
        <span>{formatShortDate(daily[0].date)}</span>
        <span>{formatShortDate(daily[Math.floor(daily.length / 2)].date)}</span>
        <span>{formatShortDate(daily[daily.length - 1].date)}</span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-gray-100 bg-gray-50 p-3 text-xs text-gray-600">
        <span className="font-medium text-gray-900">{formatShortDate(activeDay.date)}</span>
        <span>
          Real: <strong className="text-gray-900">{formatNumber(activeDay.actual_production_kwh)} kWh</strong>
        </span>
        <span>
          Esperado:{' '}
          <strong className="text-gray-900">{formatNumber(activeDay.expected_production_kwh)} kWh</strong>
        </span>
        {activeDay.deviation_percent != null && (
          <span className={SEVERITY_TEXT[activeSeverity]}>
            Desvio: {formatNumber(activeDay.deviation_percent, 1)}%
          </span>
        )}
        <span className={`inline-flex items-center gap-1 font-medium ${SEVERITY_TEXT[activeSeverity]}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${SEVERITY_DOT[activeSeverity]}`} />
          {LEVEL_LABEL[activeDay.level]}
        </span>
      </div>
    </div>
  )
}

interface AnomalyFetchState {
  data: AnomalyDashboardResponse | null
  loading: boolean
}

export function DashboardPage() {
  const { logout } = useAuth()
  const [state, setState] = useState<FetchState>({
    data: null,
    loading: true,
    error: null,
    lastUpdated: null,
  })
  const [anomalyState, setAnomalyState] = useState<AnomalyFetchState>({ data: null, loading: true })

  const fetchData = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const response = await apiFetch(
        `/energy/executive/latest?plant_id=${encodeURIComponent(PLANT_ID)}`
      )
      if (!response.ok) {
        if (response.status === 401) {
          // apiFetch already attempted refresh; if still 401 the user was logged out.
          return
        }
        throw new Error(`Erro ao buscar dados (${response.status}).`)
      }
      const data = parseExecutiveDashboard(await response.json())
      setState({ data, loading: false, error: null, lastUpdated: new Date() })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido ao buscar dados.'
      setState((prev) => ({ ...prev, loading: false, error: message }))
    }
  }, [])

  const fetchAnomalies = useCallback(async () => {
    setAnomalyState((prev) => ({ ...prev, loading: true }))
    try {
      const response = await apiFetch(
        `/energy/anomalies/latest?plant_id=${encodeURIComponent(PLANT_ID)}` +
          `&expected_daily_production_kwh=${EXPECTED_DAILY_PRODUCTION_KWH}&days=90`
      )
      if (!response.ok) {
        // Sem dado diário suficiente (404) ou sessão expirada: não é um erro que
        // deva bloquear o resto do dashboard, então falha silenciosamente aqui.
        setAnomalyState({ data: null, loading: false })
        return
      }
      const data = parseAnomalyDashboard(await response.json())
      setAnomalyState({ data, loading: false })
    } catch {
      setAnomalyState({ data: null, loading: false })
    }
  }, [])

  useEffect(() => {
    void fetchData()
    void fetchAnomalies()
  }, [fetchData, fetchAnomalies])

  const { data, loading, error, lastUpdated } = state
  const indicators = data?.current_cycle.indicators
  const quality = data?.current_cycle.quality
  const hasPartialData =
    !!quality &&
    quality.missing_days + quality.provisional_days + quality.incomplete_days + quality.unavailable_days > 0

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-900">Mplacas — Dashboard</h1>
          <button
            onClick={logout}
            className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            Sair
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col gap-3 mb-6 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-sm font-medium text-gray-600">Dashboard executivo</h2>
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="text-xs text-gray-400">
                Atualizado:{' '}
                {lastUpdated.toLocaleTimeString('pt-BR', {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })}
              </span>
            )}
            <button
              onClick={() => {
                void fetchData()
                void fetchAnomalies()
              }}
              disabled={loading}
              className="text-xs text-blue-600 hover:text-blue-800 disabled:opacity-50 transition-colors"
            >
              {loading ? 'Atualizando...' : 'Atualizar'}
            </button>
          </div>
        </div>

        {error && (
          <div
            role="alert"
            className="mb-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        {loading && !data && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm animate-pulse"
              >
                <div className="h-3 bg-gray-200 rounded w-1/2 mb-3" />
                <div className="h-7 bg-gray-200 rounded w-2/3" />
              </div>
            ))}
          </div>
        )}

        {data && indicators && quality && (
          <>
            <HeroCard
              referenceMonth={data.current_cycle.reference_month}
              headline={data.headline}
              status={data.status}
              healthScore={indicators.health_score}
            />
            <QualityBanner quality={quality} />

            {data.priority_actions.length > 0 && (
              <div className="mt-4 rounded-xl border border-gray-200 border-l-4 border-l-[var(--color-warning)] bg-white p-5 shadow-sm">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Ações prioritárias
                </p>
                <ul className="mt-3 space-y-2 text-sm text-gray-700">
                  {data.priority_actions.map((action) => (
                    <li key={action} className="flex gap-2">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-warning)]" />
                      <span>{action}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {data.trend && (
              <div className="mt-8">
                <SectionTitle>Tendência</SectionTitle>
                <TrendCard trend={data.trend} />
              </div>
            )}

            <div className="mt-8">
              <SectionTitle>Energia e produção</SectionTitle>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <MetricCard
                  label="Produção no ciclo"
                  value={indicators.cycle_production_kwh}
                  unit="kWh"
                  partial={hasPartialData}
                />
                <MetricCard
                  label="Energia importada"
                  value={indicators.imported_kwh}
                  unit="kWh"
                  partial={hasPartialData}
                />
                <MetricCard
                  label="Energia injetada"
                  value={indicators.injected_kwh}
                  unit="kWh"
                  partial={hasPartialData}
                />
                <MetricCard
                  label="Autoconsumo estimado"
                  value={indicators.estimated_self_consumption_kwh}
                  unit="kWh"
                  partial={hasPartialData}
                />
                <MetricCard
                  label="Consumo total estimado"
                  value={indicators.estimated_total_consumption_kwh}
                  unit="kWh"
                  partial={hasPartialData}
                />
                <ProductionSplitCard
                  selfConsumption={indicators.estimated_self_consumption_kwh}
                  injected={indicators.injected_kwh}
                />
              </div>
            </div>

            <div className="mt-8">
              <SectionTitle>Fluxo de energia</SectionTitle>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
                <EnergyFlowDiagram
                  production={indicators.cycle_production_kwh}
                  selfConsumption={indicators.estimated_self_consumption_kwh}
                  injected={indicators.injected_kwh}
                  imported={indicators.imported_kwh}
                  consumption={indicators.estimated_total_consumption_kwh}
                />
                <ConsumptionDonut
                  imported={indicators.imported_kwh}
                  selfConsumption={indicators.estimated_self_consumption_kwh}
                />
              </div>
            </div>

            <div className="mt-8">
              <SectionTitle>Histórico de produção</SectionTitle>
              {anomalyState.loading && !anomalyState.data ? (
                <div className="animate-pulse rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                  <div className="mb-3 h-3 w-1/3 rounded bg-gray-200" />
                  <div className="h-40 w-full rounded bg-gray-100" />
                </div>
              ) : anomalyState.data ? (
                <ProductionHistoryChart
                  daily={anomalyState.data.daily}
                  currentStreakDays={anomalyState.data.current_streak_days}
                />
              ) : (
                <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Histórico de produção diária
                  </p>
                  <p className="mt-4 text-sm text-gray-400">
                    Não foi possível carregar o histórico de produção diária no momento.
                  </p>
                </div>
              )}
            </div>

            <div className="mt-8">
              <SectionTitle>Indicadores percentuais</SectionTitle>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <MetricCard
                  label="Autossuficiência"
                  value={indicators.self_sufficiency_rate_percent}
                  unit="%"
                  barPercent={toNumber(indicators.self_sufficiency_rate_percent)}
                />
                <MetricCard
                  label="Dependência da rede"
                  value={indicators.grid_dependency_rate_percent}
                  unit="%"
                  barPercent={toNumber(indicators.grid_dependency_rate_percent)}
                />
              </div>
            </div>

            <div className="mt-8">
              <SectionTitle>Financeiro</SectionTitle>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <CurrencyCard
                  label="Componente energia da fatura"
                  value={indicators.bill_energy_component_brl}
                />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
