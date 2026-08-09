import { formatFullDate } from '../lib/format'

// Frescor real do dado, não o momento em que o navegador fez o fetch. Sempre
// que existe uma data de produção diária coletada (`latestDataDate`), ela é a
// informação mais útil para a operação: "meu dado está atualizado até quando?".
export function DataFreshness({
  latestDataDate,
  lastSyncedAt,
}: {
  latestDataDate: string | null
  lastSyncedAt: Date | null
}) {
  if (!lastSyncedAt) return null

  if (latestDataDate) {
    return (
      <span className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary)] shadow-sm">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" aria-hidden="true" />
        <span>Dado mais recente: {formatFullDate(latestDataDate)}</span>
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary)] shadow-sm">
      <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-brand-primary)]" aria-hidden="true" />
      <span>
        Sincronizado às{' '}
        {lastSyncedAt.toLocaleTimeString('pt-BR', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })}
      </span>
    </span>
  )
}
