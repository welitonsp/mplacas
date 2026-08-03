import type { TrendMetric } from '../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../lib/format'
import { DIRECTION_SYMBOL, DIRECTION_TEXT, SEVERITY_TEXT, trendSeverity, type TrendMetricKey } from '../lib/dashboard/visuals'

export function TrendMetricItem({
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
          <span className="text-xs font-normal text-gray-500">
            ({percent > 0 ? '+' : ''}
            {formatNumber(percent, 1)}% · {DIRECTION_TEXT[metric.direction]})
          </span>
        )}
      </span>
    </div>
  )
}
