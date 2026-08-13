import { OperationalState } from './OperationalState'

// Bloco de erro com retry associado diretamente à mensagem. A API pública foi
// mantida, mas agora usa o padrão visual de estado operacional para ficar
// consistente com estados vazios, carregamento e dados incompletos.
export function RetryableError({
  message,
  onRetry,
  className = '',
}: {
  message: string
  onRetry: () => void
  className?: string
}) {
  return (
    <OperationalState
      role="alert"
      tone="danger"
      icon="warning"
      align="start"
      title="Não foi possível carregar os dados"
      description={message}
      className={className}
      action={
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex min-h-[44px] shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--color-danger)] px-4 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-[var(--color-danger-text)] hover:shadow-md active:translate-y-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-danger)] focus-visible:ring-offset-2 motion-reduce:transition-none"
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
      }
    />
  )
}
