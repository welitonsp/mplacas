import type { ReactNode, Ref } from 'react'

export function PageHeader({
  eyebrow,
  title,
  description,
  headingRef,
  actions,
}: {
  eyebrow: string
  title: string
  description: string
  headingRef?: Ref<HTMLHeadingElement>
  actions?: ReactNode
}) {
  return (
    <div className="mb-6 overflow-hidden rounded-3xl border border-[var(--color-border)] bg-[linear-gradient(135deg,var(--color-surface)_0%,var(--color-surface-subtle)_100%)] p-4 shadow-sm sm:p-5">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-brand-primary)]">
            {eyebrow}
          </p>
          <h1
            ref={headingRef}
            tabIndex={-1}
            className="mt-2 rounded text-2xl font-bold tracking-tight text-gray-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] sm:text-3xl"
          >
            {title}
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">{description}</p>
        </div>
        {actions && <div className="lg:justify-self-end">{actions}</div>}
      </div>
    </div>
  )
}
