import type { MetricValue } from '../lib/dashboard/contracts'
import { clampPercent, formatNumber } from '../lib/format'

export function MetricCard({
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
        {unit && <span className="ml-1 text-sm font-normal text-gray-500">{unit}</span>}
      </p>
      {barPercent != null && (
        <div
          className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-100"
          role="progressbar"
          aria-valuenow={clampPercent(barPercent)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={label}
        >
          <div
            className="h-full rounded-full bg-[var(--color-brand-primary)]"
            style={{ width: `${clampPercent(barPercent)}%` }}
          />
        </div>
      )}
    </div>
  )
}
