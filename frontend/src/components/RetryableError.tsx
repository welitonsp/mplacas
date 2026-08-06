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
      className={`flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[var(--color-danger-light)] border border-[var(--color-danger)]/20 px-4 py-3 text-sm text-[var(--color-danger-text)] ${className}`.trim()}
    >
      <span>{message}</span>
      <button
        type="button"
        onClick={onRetry}
        className="shrink-0 rounded text-sm font-medium hover:underline transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-danger)]"
      >
        Tentar novamente
      </button>
    </div>
  )
}
