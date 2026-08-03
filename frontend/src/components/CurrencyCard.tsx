import type { MetricValue } from '../lib/dashboard/contracts'
import { formatCurrency } from '../lib/format'

export function CurrencyCard({ label, value }: { label: string; value: MetricValue }) {
  return (
    <div className="rounded-xl border border-[var(--color-brand-primary)]/20 bg-[var(--color-brand-primary-light)] p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">{formatCurrency(value)}</p>
    </div>
  )
}
