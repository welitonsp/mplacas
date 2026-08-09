import type { ChartTone } from './Gauge'
import { useChartEntrance } from './useChartEntrance'

export type StackedBarSegment = {
  label: string
  value: number
  tone?: ChartTone
}

const TONE_BG_VAR: Record<ChartTone, string> = {
  success: 'var(--color-success-text)',
  warning: 'var(--color-warning-text)',
  danger: 'var(--color-danger-text)',
  neutral: 'var(--color-brand-primary)',
}

// Altura mínima de 24px — piso mais alto que o de `BarList`/`Bullet` (20px)
// porque aqui a barra concentra vários segmentos lado a lado; abaixo disso os
// segmentos menores ficam ilegíveis (mesmo diagnóstico das barras de 6-8px
// já corrigidas no projeto, ver `chart-standards`).
const DEFAULT_HEIGHT = 24

/**
 * Barra horizontal 100% empilhada, em SVG/CSS puro, para decompor um total em
 * partes proporcionais (ex.: autossuficiência + dependência da rede,
 * decomposição de uma fatura).
 *
 * `total`, se ausente, é a soma dos `value` de `segments` — nunca um valor
 * inventado. Segmentos com `value <= 0` não são desenhados (não força um
 * traço de largura zero, mesmo princípio de `BarList` para `value: null`).
 * Quando o total efetivo é `<= 0`, a barra não tem nenhum segmento
 * desenhável — a trilha aparece vazia, mas a legenda continua listando os
 * valores reais recebidos (nunca escondida).
 */
export function StackedBar({
  segments,
  total,
  valueFormatter,
  height = DEFAULT_HEIGHT,
  className = '',
}: {
  segments: StackedBarSegment[]
  total?: number
  valueFormatter?: (value: number) => string
  height?: number
  className?: string
}) {
  const formatValue = valueFormatter ?? ((value: number) => String(value))
  const effectiveTotal = total ?? segments.reduce((sum, segment) => sum + segment.value, 0)
  const renderableSegments = segments.filter((segment) => segment.value > 0)

  // Animação de entrada (uma vez por montagem, nunca em refetch — ver
  // `useChartEntrance`): os segmentos crescem juntos de 0% até sua largura
  // real. `aria-label`/a legenda com os valores nunca dependem disto.
  const entered = useChartEntrance()

  const ariaLabel = (() => {
    const totalText = `Total ${formatValue(effectiveTotal)}`
    if (renderableSegments.length === 0) return totalText
    const parts = renderableSegments.map(
      (segment) => `${segment.label} ${formatValue(segment.value)}`,
    )
    return `${totalText}: ${parts.join(', ')}`
  })()

  if (segments.length === 0) {
    return <p className={`text-sm text-gray-500 ${className}`.trim()}>Nenhum dado para exibir.</p>
  }

  return (
    <div className={`flex flex-col gap-3 ${className}`.trim()}>
      <div
        role="img"
        aria-label={ariaLabel}
        className="flex w-full overflow-hidden rounded-full bg-[var(--color-chart-track)] shadow-inner ring-1 ring-inset ring-black/5"
        style={{ height }}
      >
        {effectiveTotal > 0 &&
          renderableSegments.map((segment, index) => {
            const pct = Math.min(Math.max((segment.value / effectiveTotal) * 100, 0), 100)
            const color = TONE_BG_VAR[segment.tone ?? 'neutral']
            return (
              <div
                key={`${segment.label}-${index}`}
                title={`${segment.label}: ${formatValue(segment.value)}`}
                aria-hidden="true"
                className="h-full shadow-[inset_0_1px_0_rgba(255,255,255,0.28)] transition-[width] duration-300 ease-out motion-reduce:transition-none first:rounded-l-full last:rounded-r-full"
                style={{
                  width: `${entered ? pct : 0}%`,
                  background: `linear-gradient(90deg, ${color}, color-mix(in srgb, ${color} 74%, white))`,
                }}
              />
            )
          })}
      </div>
      <ul className="flex flex-wrap gap-2 text-sm" aria-hidden="true">
        {segments.map((segment, index) => (
          <li
            key={`${segment.label}-legend-${index}`}
            className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 shadow-sm"
          >
            <span
              className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
              style={{
                backgroundColor:
                  segment.value > 0 ? TONE_BG_VAR[segment.tone ?? 'neutral'] : 'var(--color-chart-track)',
              }}
            />
            <span className="text-gray-600">{segment.label}</span>
            <span className="font-semibold tabular-nums text-[var(--color-text-primary)]">
              {formatValue(segment.value)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
