import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { apiFetch } from '../lib/api'
import { PLANT_ID } from '../env'

type MetricValue = string | number | null

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

function MetricCard({
  label,
  value,
  unit,
}: {
  label: string
  value: MetricValue
  unit?: string
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">
        {formatNumber(value)}
        {value != null && unit && (
          <span className="ml-1 text-sm font-normal text-gray-500">{unit}</span>
        )}
      </p>
    </div>
  )
}

function CurrencyCard({ label, value }: { label: string; value: MetricValue }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">{formatCurrency(value)}</p>
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
          <div>
            <h2 className="text-sm font-medium text-gray-600">Dashboard executivo</h2>
            {data && (
              <p className="mt-1 text-xl font-semibold text-gray-900">{data.headline}</p>
            )}
          </div>
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

        {data && indicators && (
          <>
            <div className="mb-4 rounded-xl bg-white border border-gray-200 p-5 shadow-sm">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Ciclo de referência
                  </p>
                  <p className="mt-1 text-lg font-semibold text-gray-900">
                    {data.current_cycle.reference_month}
                  </p>
                </div>
                <div className="text-sm text-gray-500">
                  Status: <span className="font-medium text-gray-900">{data.status}</span>
                </div>
              </div>
              {quality && (
                <p className="mt-3 text-xs text-gray-500">
                  Qualidade dos dados: {quality.missing_days} ausentes,{' '}
                  {quality.provisional_days} provisórios, {quality.incomplete_days} incompletos e{' '}
                  {quality.unavailable_days} indisponíveis.
                </p>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <MetricCard
                label="Produção no ciclo"
                value={indicators.cycle_production_kwh}
                unit="kWh"
              />
              <MetricCard label="Energia importada" value={indicators.imported_kwh} unit="kWh" />
              <MetricCard label="Energia injetada" value={indicators.injected_kwh} unit="kWh" />
              <MetricCard
                label="Autoconsumo estimado"
                value={indicators.estimated_self_consumption_kwh}
                unit="kWh"
              />
              <MetricCard
                label="Consumo total estimado"
                value={indicators.estimated_total_consumption_kwh}
                unit="kWh"
              />
              <MetricCard
                label="Autossuficiência"
                value={indicators.self_sufficiency_rate_percent}
                unit="%"
              />
              <MetricCard
                label="Dependência da rede"
                value={indicators.grid_dependency_rate_percent}
                unit="%"
              />
              <MetricCard label="Saúde da usina" value={indicators.health_score} />
              <CurrencyCard
                label="Componente energia da fatura"
                value={indicators.bill_energy_component_brl}
              />
            </div>

            {data.priority_actions.length > 0 && (
              <div className="mt-6 rounded-xl bg-white border border-gray-200 p-5 shadow-sm">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Ações prioritárias
                </p>
                <ul className="mt-3 space-y-2 text-sm text-gray-700 list-disc list-inside">
                  {data.priority_actions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ul>
              </div>
            )}

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
