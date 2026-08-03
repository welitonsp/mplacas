import type { CycleQuality } from '../lib/dashboard/contracts'

export function QualityBanner({ quality }: { quality: CycleQuality }) {
  const items = [
    { key: 'missing', label: 'ausente', value: quality.missing_days },
    { key: 'provisional', label: 'provisório', value: quality.provisional_days },
    { key: 'incomplete', label: 'incompleto', value: quality.incomplete_days },
    { key: 'unavailable', label: 'indisponível', value: quality.unavailable_days },
  ].filter((item) => item.value > 0)

  if (items.length === 0) {
    return (
      <p className="mt-4 flex items-center gap-1.5 text-xs text-[var(--color-success)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
        Dados consolidados — nenhuma pendência neste ciclo.
      </p>
    )
  }

  return (
    <div className="mt-4 rounded-xl border border-dashed border-[var(--color-warning)] bg-[var(--color-warning-light)] p-4">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-warning)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-warning)]" />
        Dados parciais neste ciclo
      </p>
      <p className="mt-1.5 text-sm text-gray-700">
        {items
          .map((item) => `${item.value} dia${item.value > 1 ? 's' : ''} ${item.label}${item.value > 1 ? 's' : ''}`)
          .join(', ')}
        .
      </p>
    </div>
  )
}
