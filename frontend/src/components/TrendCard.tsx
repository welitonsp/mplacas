import type { ExecutiveTrend, Severity } from '../lib/dashboard/contracts'
import { formatCycleLabel, formatNumber, toNumber } from '../lib/format'
import { SEVERITY_TEXT } from '../lib/dashboard/visuals'
import { Card } from './Card'
import { TrendMetricItem } from './TrendMetricItem'
import { Sparkline } from './charts/Sparkline'

function formatPoints(value: number): string {
  return `${Math.abs(value).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} p.p.`
}

export function TrendCard({ trend }: { trend: ExecutiveTrend }) {
  const points = toNumber(trend.metrics.self_sufficiency_delta_points)
  const pointsSeverity: Severity = points == null || points === 0 ? 'neutral' : points > 0 ? 'success' : 'danger'

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500">
        Comparação com o ciclo anterior
      </p>
      <p className="mt-1 text-xs text-gray-500">
        {formatCycleLabel(trend.previous_reference_month)} → {formatCycleLabel(trend.current_reference_month)}
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
          <div className="flex flex-col items-end gap-1">
            <span className={`text-sm font-semibold tabular-nums ${SEVERITY_TEXT[pointsSeverity]}`}>
              {points != null && points > 0 ? '+' : ''}
              {formatNumber(points, 1)} p.p.
            </span>
            {points != null && (
              <Sparkline
                percentDelta={points}
                label="Autossuficiência"
                valueFormatter={formatPoints}
                tone={pointsSeverity}
                className="w-24"
              />
            )}
          </div>
        </div>
      </div>
    </Card>
  )
}
