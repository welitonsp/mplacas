import type { AnomalyFetchState } from '../lib/dashboard/contracts'
import { toNumber } from '../lib/format'
import { ProductionHistoryChart } from './ProductionHistoryChart'
import { YieldCard } from './YieldCard'

export function ProductionHistorySection({ anomalyState }: { anomalyState: AnomalyFetchState }) {
  if (anomalyState.loading && !anomalyState.data) {
    return (
      <div className="animate-pulse rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="mb-3 h-3 w-1/3 rounded bg-gray-200" />
        <div className="h-40 w-full rounded bg-gray-100" />
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
