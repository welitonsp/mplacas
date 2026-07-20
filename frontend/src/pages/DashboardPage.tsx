import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { apiFetch } from '../lib/api'
import { PLANT_ID } from '../env'

interface EnergyReading {
  plant_id: string
  timestamp: string
  active_power_kw: number | null
  energy_today_kwh: number | null
  energy_month_kwh: number | null
  energy_total_kwh: number | null
  irradiance_wm2: number | null
  performance_ratio: number | null
}

interface FetchState {
  data: EnergyReading | null
  loading: boolean
  error: string | null
  lastUpdated: Date | null
}

function MetricCard({
  label,
  value,
  unit,
}: {
  label: string
  value: number | null | undefined
  unit: string
}) {
  const formatted =
    value == null
      ? '—'
      : value.toLocaleString('pt-BR', { maximumFractionDigits: 2 })

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">
        {formatted}
        {value != null && (
          <span className="ml-1 text-sm font-normal text-gray-500">{unit}</span>
        )}
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
          // apiFetch already attempted refresh; if still 401 the user was logged out
          return
        }
        throw new Error(`Erro ao buscar dados (${response.status}).`)
      }
      const data = (await response.json()) as EnergyReading
      setState({ data, loading: false, error: null, lastUpdated: new Date() })
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Erro desconhecido ao buscar dados.'
      setState((prev) => ({ ...prev, loading: false, error: message }))
    }
  }, [])

  useEffect(() => {
    void fetchData()
  }, [fetchData])

  const { data, loading, error, lastUpdated } = state

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
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

      {/* Main */}
      <main className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-8">
        {/* Status bar */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-sm font-medium text-gray-600">Dados em tempo real</h2>
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

        {/* Error state */}
        {error && (
          <div
            role="alert"
            className="mb-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        {/* Loading skeleton */}
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

        {/* Data grid */}
        {data && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <MetricCard
              label="Potência Ativa"
              value={data.active_power_kw}
              unit="kW"
            />
            <MetricCard
              label="Energia Hoje"
              value={data.energy_today_kwh}
              unit="kWh"
            />
            <MetricCard
              label="Energia no Mês"
              value={data.energy_month_kwh}
              unit="kWh"
            />
            <MetricCard
              label="Energia Total"
              value={data.energy_total_kwh}
              unit="kWh"
            />
            <MetricCard
              label="Irradiância"
              value={data.irradiance_wm2}
              unit="W/m²"
            />
            <MetricCard
              label="Performance Ratio"
              value={
                data.performance_ratio != null
                  ? data.performance_ratio * 100
                  : null
              }
              unit="%"
            />
          </div>
        )}

        {/* Timestamp footer */}
        {data && (
          <p className="mt-6 text-xs text-gray-400 text-right">
            Leitura do servidor:{' '}
            {new Date(data.timestamp).toLocaleString('pt-BR', {
              dateStyle: 'short',
              timeStyle: 'medium',
            })}
          </p>
        )}
      </main>
    </div>
  )
}
