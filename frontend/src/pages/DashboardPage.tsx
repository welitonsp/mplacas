import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { apiFetch } from '../lib/api'
import { PLANT_ID } from '../env'
import type { AnomalyFetchState, FetchState } from '../lib/dashboard/contracts'
import { parseAnomalyDashboard, parseExecutiveDashboard } from '../lib/dashboard/contracts'
import { EXPECTED_DAILY_PRODUCTION_KWH } from '../lib/dashboard/yield'
import { toNumber } from '../lib/format'
import { SectionTitle } from '../components/SectionTitle'
import { MetricCard } from '../components/MetricCard'
import { CurrencyCard } from '../components/CurrencyCard'
import { HeroCard } from '../components/HeroCard'
import { QualityBanner } from '../components/QualityBanner'
import { TrendCard } from '../components/TrendCard'
import { ProductionSplitCard } from '../components/ProductionSplitCard'
import { EnergyFlowDiagram } from '../components/EnergyFlowDiagram'
import { ConsumptionDonut } from '../components/ConsumptionDonut'
import { DashboardHeader } from '../components/DashboardHeader'
import { MetricCardSkeletonGrid } from '../components/MetricCardSkeletonGrid'
import { PriorityActionsCard } from '../components/PriorityActionsCard'
import { ProductionHistorySection } from '../components/ProductionHistorySection'

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
      <DashboardHeader onLogout={logout} />

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

        {loading && !data && <MetricCardSkeletonGrid />}

        {data && indicators && quality && (
          <>
            <HeroCard
              referenceMonth={data.current_cycle.reference_month}
              headline={data.headline}
              status={data.status}
              healthScore={indicators.health_score}
            />
            <QualityBanner quality={quality} />

            <PriorityActionsCard actions={data.priority_actions} />

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
              <ProductionHistorySection anomalyState={anomalyState} />
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
