import type { AnomalyFetchState } from '../lib/dashboard/contracts'
import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'
import { baselineUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { toNumber } from '../lib/format'
import { ProductionHistoryChart } from './ProductionHistoryChart'
import { YieldCard } from './YieldCard'

export function ProductionHistorySection({
  anomalyState,
  expectedProduction,
}: {
  anomalyState: AnomalyFetchState
  // `null` = baseline sazonal ainda carregando.
  expectedProduction: ExpectedDailyProduction | null
}) {
  const loadingExpected = expectedProduction === null
  const loadingHistory = expectedProduction?.available === true && anomalyState.loading && !anomalyState.data

  if (loadingExpected || loadingHistory) {
    return (
      <div className="animate-pulse rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="mb-3 h-3 w-1/3 rounded bg-gray-200" />
        <div className="h-40 w-full rounded bg-gray-100" />
      </div>
    )
  }

  // Produção esperada indisponível (ver os três motivos em
  // `photovoltaic-contracts.ts`): sem ela o backend não classifica anomalia por
  // dia, então nem chegamos a buscar o histórico. Mostramos o motivo específico
  // em vez de um card vazio (ver skill frontend-design).
  if (!expectedProduction.available) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Histórico de produção diária
        </p>
        <p className="mt-4 text-sm text-gray-500">
          {baselineUnavailableMessage(expectedProduction.reason, expectedProduction.referenceCompleteOn)}
        </p>
      </div>
    )
  }

  if (!anomalyState.data) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Histórico de produção diária
        </p>
        <p className="mt-4 text-sm text-gray-400">
          Não foi possível carregar o histórico de produção diária no momento.
        </p>
      </div>
    )
  }

  const hasIrradiation = anomalyState.data.daily.some((d) => toNumber(d.irradiation_kwh_m2) != null)

  return (
    <div className={hasIrradiation ? 'grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]' : ''}>
      <ProductionHistoryChart
        daily={anomalyState.data.daily}
        currentStreakDays={anomalyState.data.current_streak_days}
      />
      <YieldCard daily={anomalyState.data.daily} />
    </div>
  )
}
