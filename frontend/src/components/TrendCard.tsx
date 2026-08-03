import type { ExecutiveTrend, Severity } from '../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../lib/format'
import { SEVERITY_TEXT } from '../lib/dashboard/visuals'
import { TrendMetricItem } from './TrendMetricItem'

export function TrendCard({ trend }: { trend: ExecutiveTrend }) {
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
