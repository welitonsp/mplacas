import type { ReactNode, Ref } from 'react'
import { Link } from 'react-router'

export function PageHeader({
  eyebrow,
  title,
  description,
  headingRef,
  actions,
  insights,
  backLink,
}: {
  eyebrow: string
  title: string
  description: string
  headingRef?: Ref<HTMLHeadingElement>
  actions?: ReactNode
  insights?: ReadonlyArray<{ label: string; value: string }>
  // Subpágina de uma aba (ex.: Detalhes técnicos, dentro de Energia): volta
  // para a aba-mãe sem depender do botão voltar do navegador.
  backLink?: { to: string; label: string }
}) {
  // Cabeçalho do módulo SEM cartão em volta (ADR-077): título direto sobre o
  // fundo da página, como em Fluent/Material. O cartão anterior com gradiente
  // somava mais uma moldura a uma tela que já era só molduras.
  return (
    <header className="mb-6 sm:mb-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          {backLink && (
            <Link
              to={backLink.to}
              className="-ml-1 mb-1 inline-flex min-h-[44px] items-center gap-1 rounded px-1 text-sm font-semibold text-[var(--color-brand-primary)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
            >
              <span aria-hidden="true">←</span> {backLink.label}
            </Link>
          )}
          <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">{eyebrow}</p>
          <h1
            ref={headingRef}
            tabIndex={-1}
            className="mt-1 rounded text-[28px] font-semibold leading-[1.15] text-[var(--color-text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] sm:text-[34px]"
          >
            {title}
          </h1>
          <p className="mt-2 max-w-2xl text-[15px] leading-6 text-[var(--color-text-secondary)]">{description}</p>
        </div>
        {actions && <div className="min-w-0 max-w-full">{actions}</div>}
      </div>

      {insights && insights.length > 0 && (
        <dl
          aria-label="Leitura executiva do módulo"
          className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-[13px]"
        >
          {insights.map((insight) => (
            <div key={`${insight.label}-${insight.value}`} className="flex gap-1.5">
              <dt className="text-[var(--color-text-secondary)]">{insight.label}:</dt>
              <dd className="font-semibold text-[var(--color-text-primary)]">{insight.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </header>
  )
}
