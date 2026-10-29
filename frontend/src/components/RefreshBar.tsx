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

  const idle = !loading && requestedAt === null
  const statusText = loading
    ? 'Sincronizando dados do painel'
    : requestedAt
      ? `Atualização solicitada às ${requestedAt.toLocaleTimeString('pt-BR', {
          hour: '2-digit',
          minute: '2-digit',
          timeZone: 'America/Sao_Paulo',
        })}`
      : 'Dados podem ser sincronizados manualmente'

  // Ação secundária discreta (ADR-077): status em texto simples ao lado de um
  // botão contornado. Antes eram duas pílulas empilhadas com sombra e efeito
  // de levantar, que pareciam conteúdo e quebravam o alinhamento do cabeçalho.
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-2 ${className}`.trim()}>
      {/* Em repouso o texto é neutro: nada aconteceu, então nada de bolinha
          verde (verde, no MPlacas, é energia/"tudo certo"). No celular o texto
          de repouso some — só o botão, para o conteúdo subir; durante e depois
          da atualização o retorno aparece em qualquer tela. */}
      <p
        aria-live="polite"
        className={`items-center gap-2 text-[13px] text-[var(--color-text-secondary)] ${idle ? 'hidden sm:inline-flex' : 'inline-flex'}`}
      >
        {loading && <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-[var(--color-brand-primary)]" />}
        {statusText}
      </p>

      <button
        type="button"
        onClick={handleRefresh}
        disabled={loading}
        className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-[var(--radius-control)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 text-sm font-semibold text-[var(--color-text-primary)] transition-colors duration-150 hover:border-[var(--color-gray-300)] hover:bg-[var(--color-gray-50)] disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface-subtle)] motion-reduce:transition-none"
      >
        <svg
          viewBox="0 0 20 20"
          aria-hidden="true"
          className={`h-4 w-4 ${loading ? 'animate-spin motion-reduce:animate-none' : ''}`}
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
  )
}
