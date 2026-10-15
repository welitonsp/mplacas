import type { ReactNode, Ref } from 'react'

export function PageHeader({
  eyebrow,
  title,
  description,
  headingRef,
  actions,
  insights,
}: {
  eyebrow: string
  title: string
  description: string
  headingRef?: Ref<HTMLHeadingElement>
  actions?: ReactNode
  insights?: ReadonlyArray<{ label: string; value: string }>
}) {
  // Cabeçalho do módulo SEM cartão em volta (ADR-077): título direto sobre o
  // fundo da página, como em Fluent/Material. O cartão anterior com gradiente
  // somava mais uma moldura a uma tela que já era só molduras.
  return (
    <header className="mb-6 sm:mb-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
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
        {actions && <div className="shrink-0">{actions}</div>}
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
