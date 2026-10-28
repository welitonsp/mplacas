import type { ReactNode } from 'react'

// Esqueleto único de card, reaproveitado por todos os cards de métrica/estado
// do dashboard (Etapa 8 — antes disso, `MetricCard`/`CurrencyCard`/`HeroCard`/
// `QualityBanner` e vários cards inline cada um definia sua própria borda/
// fundo/sombra). `CurrencyCard` deliberadamente usa `tone="neutral"` (mesmo
// visual do `MetricCard` padrão) — um valor financeiro não deve parecer
// banner promocional, é só um dado com formatação diferente.
//
// Sem `accent` (faixa lateral colorida de 4 px) desde o refinamento da
// ADR-077: a decisão 18 manda a cor de estado só no texto/ícone do valor, e
// a faixa ainda deformava o canto arredondado do cartão.
export type CardTone = 'neutral' | 'warning' | 'danger'

export function Card({
  dashed = false,
  tone = 'neutral',
  padding = 'p-4 sm:p-5',
  className = '',
  // `hover:shadow-md` só faz sentido quando o card responde a interação
  // (é clicável/expansível) — aplicado incondicionalmente antes, sinalizava
  // "clicável" em cards que só exibem dado (ver acabamento de hierarquia
  // visual do dashboard).
  interactive = false,
  children,
  ...rest
}: {
  dashed?: boolean
  tone?: CardTone
  // Utilitário de padding sobrescrevível (ex: `QualityBanner` usa `p-4`) — separado
  // de `className` para nunca colidir com o `p-4 sm:p-5` padrão na mesma cascata CSS.
  padding?: string
  className?: string
  interactive?: boolean
  children: ReactNode
} & React.HTMLAttributes<HTMLDivElement>) {
  const toneClass =
    tone === 'warning'
      ? 'bg-[var(--color-warning-light)] border-[var(--color-warning)]'
      : tone === 'danger'
        ? 'bg-[var(--color-danger-light)] border-[var(--color-danger)]/30'
        : 'bg-[var(--color-surface)] border-[var(--color-border)]'
  const interactiveClass = interactive
    ? 'hover:border-[var(--color-gray-300)] hover:-translate-y-0.5 active:translate-y-0'
    : ''

  return (
    <div
      className={`relative rounded-[var(--radius-card)] border ${dashed ? 'border-dashed' : ''} ${toneClass} ${padding} shadow-[var(--shadow-card)] transition-all duration-200 ease-out motion-reduce:transition-none ${interactiveClass} ${className}`
        .replace(/\s+/g, ' ')
        .trim()}
      {...rest}
    >
      {children}
    </div>
  )
}
