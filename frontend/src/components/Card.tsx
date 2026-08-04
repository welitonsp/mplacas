import type { ReactNode } from 'react'
import type { Severity } from '../lib/dashboard/contracts'
import { SEVERITY_BORDER_L } from '../lib/dashboard/visuals'

// Esqueleto único de card, reaproveitado por todos os cards de métrica/estado
// do dashboard (Etapa 8 — antes disso, `MetricCard`/`CurrencyCard`/`HeroCard`/
// `QualityBanner` e vários cards inline cada um definia sua própria borda/
// fundo/sombra). `CurrencyCard` deliberadamente usa `tone="neutral"` (mesmo
// visual do `MetricCard` padrão) — um valor financeiro não deve parecer
// banner promocional, é só um dado com formatação diferente.
export type CardTone = 'neutral' | 'warning' | 'danger'

export function Card({
  dashed = false,
  tone = 'neutral',
  accent,
  padding = 'p-5',
  className = '',
  children,
  ...rest
}: {
  dashed?: boolean
  tone?: CardTone
  accent?: Severity
  // Utilitário de padding sobrescrevível (ex: `QualityBanner` usa `p-4`) — separado
  // de `className` para nunca colidir com o `p-5` padrão na mesma cascata CSS.
  padding?: string
  className?: string
  children: ReactNode
} & React.HTMLAttributes<HTMLDivElement>) {
  const toneClass =
    tone === 'warning'
      ? 'bg-[var(--color-warning-light)] border-[var(--color-warning)]'
      : tone === 'danger'
        ? 'bg-[var(--color-danger-light)] border-[var(--color-danger)]/30'
        : 'bg-white border-gray-200'
  const accentClass = accent ? `border-l-4 ${SEVERITY_BORDER_L[accent]}` : ''

  return (
    <div
      className={`relative rounded-xl border ${dashed ? 'border-dashed' : ''} ${toneClass} ${padding} shadow-sm transition-shadow duration-150 hover:shadow-md ${accentClass} ${className}`
        .replace(/\s+/g, ' ')
        .trim()}
      {...rest}
    >
      {children}
    </div>
  )
}
