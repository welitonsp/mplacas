import type { MetricValue } from '../lib/dashboard/contracts'
import { clampPercent, formatNumber } from '../lib/format'
import { Card } from './Card'

export function MetricCard({
  label,
  value,
  unit,
  partial,
  barPercent,
  maximumFractionDigits,
  className,
}: {
  label: string
  value: MetricValue
  unit?: string
  partial?: boolean
  barPercent?: number | null
  // Tarifas em R$/kWh precisam de mais casas decimais que o padrão de 2 (ver
  // ADR-056) para não arredondar um valor como R$ 0,175126/kWh para R$ 0,18.
  maximumFractionDigits?: number
  className?: string
}) {
  return (
    <Card dashed={partial} className={className}>
      {partial && (
        <span className="absolute right-3 top-3 rounded-full bg-[var(--color-warning-light)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-warning)]">
          Parcial
        </span>
      )}
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">
        {formatNumber(value, maximumFractionDigits)}
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
    </Card>
  )
}
