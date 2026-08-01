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

interface ExecutiveTrend {
  current_reference_month: string
  previous_reference_month: string
}

interface ExecutiveDashboardResponse {
  plant_id: string
  status: string
  headline: string
  priority_actions: string[]
  current_cycle: ExecutiveCycle
  trend: ExecutiveTrend | null
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

function optionalTrend(source: Record<string, unknown>): ExecutiveTrend | null {
  const trend = source.trend
  if (trend === null) return null
  if (!isRecord(trend)) throw new Error('Resposta inválida da API: trend')
  return {
    current_reference_month: requireString(trend, 'current_reference_month'),
    previous_reference_month: requireString(trend, 'previous_reference_month'),
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

export function DashboardPage() {
  const { logout } = useAuth()
  const [state, setState] = useState<FetchState>({
    data: null,
    loading: true,
    error: null,
    lastUpdated: null,
  })

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

  useEffect(() => {
    void fetchData()
  }, [fetchData])

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
              onClick={() => void fetchData()}
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

            {data.trend && (
              <p className="mt-6 text-xs text-gray-400 text-right">
                Tendência calculada entre {data.trend.previous_reference_month} e{' '}
                {data.trend.current_reference_month}.
              </p>
            )}
          </>
        )}
      </main>
    </div>
  )
}
