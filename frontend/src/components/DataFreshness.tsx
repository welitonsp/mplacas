import { formatFullDate } from '../lib/format'

// Frescor real do dado, não o momento em que o navegador fez o fetch. Sempre que
// existe um dia com produção diária de fato coletada (`latestDataDate`), mostramos
// essa data — é a informação que importa para o dono da usina ("meu dado está
// atualizado até quando?"). Só caímos para o horário de sincronização quando ainda
// não há nenhum dado diário disponível para derivar essa data.
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
      <span className="text-xs text-[var(--color-text-secondary)]">
        Dado mais recente: {formatFullDate(latestDataDate)}
      </span>
    )
  }

  return (
    <span className="text-xs text-[var(--color-text-secondary)]">
      Sincronizado às{' '}
      {lastSyncedAt.toLocaleTimeString('pt-BR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })}
    </span>
  )
}
