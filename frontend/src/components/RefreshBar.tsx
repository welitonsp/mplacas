import { useState } from 'react'

// Barra de ação "Atualizar" compartilhada pelos módulos do painel.
// Mantém a API simples (`onRefresh` + `loading`) e acrescenta feedback
// operacional local: o usuário vê quando pediu uma atualização e quando a
// sincronização está em andamento, sem alterar o fluxo de dados de cada página.
export function RefreshBar({
  onRefresh,
  loading,
  className = 'mb-6',
}: {
  onRefresh: () => void
  loading: boolean
  className?: string
}) {
  const [requestedAt, setRequestedAt] = useState<Date | null>(null)

  function handleRefresh() {
    setRequestedAt(new Date())
    onRefresh()
  }

  const statusText = loading
    ? 'Sincronizando dados do painel'
    : requestedAt
      ? `Atualização solicitada às ${requestedAt.toLocaleTimeString('pt-BR', {
          hour: '2-digit',
          minute: '2-digit',
          timeZone: 'America/Sao_Paulo',
        })}`
      : 'Dados podem ser sincronizados manualmente'

  return (
    <div className={`flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end ${className}`.trim()}>
      <div className="flex flex-col items-start gap-2 sm:items-end">
        <p
          aria-live="polite"
          className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary)] shadow-sm"
        >
          <span
            aria-hidden="true"
            className={`h-1.5 w-1.5 rounded-full ${loading ? 'animate-pulse bg-[var(--color-brand-primary)]' : 'bg-[var(--color-success)]'}`}
          />
          {statusText}
        </p>

        <button
          type="button"
          onClick={handleRefresh}
          disabled={loading}
          className="group inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full border border-[var(--color-brand-primary)]/20 bg-[var(--color-brand-primary-light)] px-4 text-xs font-semibold text-[var(--color-brand-primary)] shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--color-brand-primary)]/35 hover:bg-white hover:text-[var(--color-brand-primary-dark)] hover:shadow-md active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:bg-[var(--color-brand-primary-light)] disabled:hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface-subtle)] motion-reduce:transition-none"
        >
          <svg
            viewBox="0 0 20 20"
            aria-hidden="true"
            className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : 'transition-transform duration-200 group-hover:rotate-12 motion-reduce:transition-none'}`}
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M16.2 8.2A6.5 6.5 0 0 0 4.7 5.1L3.5 6.3" />
            <path d="M3.5 3v3.3h3.3" />
            <path d="M3.8 11.8a6.5 6.5 0 0 0 11.5 3.1l1.2-1.2" />
            <path d="M16.5 17v-3.3h-3.3" />
          </svg>
          {loading ? 'Atualizando...' : 'Atualizar'}
        </button>
      </div>
    </div>
  )
}
