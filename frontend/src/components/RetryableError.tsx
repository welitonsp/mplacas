// Bloco de erro com retry associado diretamente à mensagem — extraído de
// `DashboardPage`, onde aparecia duas vezes de forma idêntica (erro global do
// dashboard executivo e erro de retorno do investimento). Mesmo padrão usado
// pelo erro de servidor do histórico de produção (`ProductionHistorySection`).
export function RetryableError({
  message,
  onRetry,
  className = '',
}: {
  message: string
  onRetry: () => void
  // Extra classes do container (ex: `mb-6` quando o bloco precisa de espaço
  // abaixo dele mesmo, fora de uma seção que já controla o espaçamento).
  className?: string
}) {
  return (
    <div
      role="alert"
      className={`rounded-2xl border border-[var(--color-danger)]/25 bg-[var(--color-danger-light)] p-4 text-[var(--color-danger-text)] shadow-sm ${className}`.trim()}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/70 ring-1 ring-inset ring-[var(--color-danger)]/15" aria-hidden="true">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 8v4" />
              <path d="M12 16h.01" />
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
            </svg>
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold">Não foi possível carregar os dados</p>
            <p className="mt-1 text-sm leading-6">{message}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex min-h-[40px] shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--color-danger)] px-4 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-[var(--color-danger-text)] hover:shadow-md active:translate-y-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-danger)] focus-visible:ring-offset-2 motion-reduce:transition-none"
        >
          <svg
            viewBox="0 0 20 20"
            aria-hidden="true"
            className="h-4 w-4"
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
          Tentar novamente
        </button>
      </div>
    </div>
  )
}
