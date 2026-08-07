import type { ChartTone } from './Gauge'

const TONE_BG_VAR: Record<ChartTone, string> = {
  success: 'var(--color-success-text)',
  warning: 'var(--color-warning-text)',
  danger: 'var(--color-danger-text)',
  neutral: 'var(--color-brand-primary)',
}

// Cor do eixo central (delta zero) — sempre neutra/escura, mesmo padrão do
// tick de meta em `Bullet` (não é um dos tokens de severidade, é referência
// de escala).
const AXIS_COLOR = 'var(--color-gray-400)'

// Altura mínima de barra do projeto (ver skill chart-standards) — barras de
// 6-8px lêem como decoração, não dado.
const BAR_HEIGHT_CLASS = 'h-4'

function defaultFormatter(n: number): string {
  return `${Math.abs(n).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`
}

/**
 * Barra de delta divergente centrada em zero, em SVG/CSS puro.
 *
 * `TrendCard`/`TrendMetricItem` comparam sempre DOIS pontos (ciclo atual vs.
 * ciclo anterior) — não uma série temporal longa — por isso a primitiva
 * certa aqui não é uma sparkline de linha, é uma barra que cresce a partir
 * de um eixo central (delta = 0): para a direita quando `percentDelta > 0`,
 * para a esquerda quando `percentDelta < 0`. O lado da barra codifica o
 * sinal (não só a cor — ver skill accessible-charts).
 *
 * `percentDelta === null` (indisponível) e `percentDelta === 0` (sem
 * variação) são estados explícitos, nunca uma barra fabricada em direção
 * arbitrária.
 */
export function Sparkline({
  percentDelta,
  maxAbsPercent,
  label,
  valueFormatter,
  tone = 'neutral',
  className = '',
}: {
  percentDelta: number | null
  // Escala do eixo (magnitude máxima representável de cada lado). Se
  // ausente, usa a magnitude do próprio delta com folga de 20% (mínimo de
  // 10 pontos percentuais de escala, para sempre haver alguma referência
  // visual mesmo com deltas pequenos).
  maxAbsPercent?: number
  label?: string
  valueFormatter?: (value: number) => string
  tone?: ChartTone
  className?: string
}) {
  const formatValue = valueFormatter ?? defaultFormatter
  const prefix = label ? `${label}: ` : ''

  if (percentDelta == null) {
    return (
      <div className={`flex flex-col gap-1 ${className}`.trim()}>
        <div
          role="status"
          aria-label={`${prefix}variação percentual indisponível`}
          className={`relative w-full overflow-hidden rounded-md border border-dashed border-[var(--color-chart-track)] ${BAR_HEIGHT_CLASS}`}
        >
          <div
            className="absolute top-0 bottom-0 left-1/2 w-px -translate-x-1/2"
            style={{ backgroundColor: AXIS_COLOR }}
            aria-hidden="true"
          />
        </div>
      </div>
    )
  }

  const safeDelta = Number.isFinite(percentDelta) ? percentDelta : 0
  const naturalMax = Math.max(Math.abs(safeDelta), 10) * 1.2
  const effectiveMax = maxAbsPercent != null && maxAbsPercent > 0 ? maxAbsPercent : naturalMax

  // Cada lado do eixo ocupa 50% da largura do contêiner — a barra nunca
  // ultrapassa esse limite, mesmo que |percentDelta| exceda effectiveMax.
  const halfWidthPct =
    effectiveMax > 0 ? Math.min(Math.max((Math.abs(safeDelta) / effectiveMax) * 50, 0), 50) : 0

  const color = TONE_BG_VAR[tone]

  const ariaLabel = (() => {
    if (safeDelta === 0) return `${prefix}sem variação em relação ao ciclo anterior`
    const directionWord = safeDelta > 0 ? 'aumentou' : 'diminuiu'
    return `${prefix}${directionWord} ${formatValue(safeDelta)} em relação ao ciclo anterior`
  })()

  const barStyle =
    safeDelta > 0
      ? { left: '50%', width: `${halfWidthPct}%` }
      : { left: `${50 - halfWidthPct}%`, width: `${halfWidthPct}%` }

  return (
    <div className={`flex flex-col gap-1 ${className}`.trim()}>
      <div
        role="img"
        aria-label={ariaLabel}
        className={`relative w-full overflow-hidden rounded-md bg-[var(--color-chart-track)] ${BAR_HEIGHT_CLASS}`}
      >
        {safeDelta !== 0 && (
          <div
            className="absolute top-0 h-full rounded-sm transition-[width] duration-150"
            style={{ ...barStyle, backgroundColor: color }}
            aria-hidden="true"
          />
        )}
        <div
          className="absolute top-0 bottom-0 left-1/2 w-px -translate-x-1/2"
          style={{ backgroundColor: AXIS_COLOR }}
          aria-hidden="true"
        />
      </div>
    </div>
  )
}
