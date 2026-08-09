import type { ChartTone } from './Gauge'
import { useChartEntrance } from './useChartEntrance'

// Cor do tick de referência (target) — sempre neutra/escura, nunca um dos
// tokens de severidade (`Gauge`/`BarList` reservam essas cores para o
// preenchimento da barra em si). Mantido como constante local para não
// inventar um token novo em `index.css` para um único traço de 2px.
const TARGET_TICK_COLOR = 'var(--color-gray-900)'

const TONE_BG_VAR: Record<ChartTone, string> = {
  success: 'var(--color-success-text)',
  warning: 'var(--color-warning-text)',
  danger: 'var(--color-danger-text)',
  neutral: 'var(--color-brand-primary)',
}

const DEVIATION_TONE_CLASS: Record<ChartTone, string> = {
  success: 'text-[var(--color-success-text)]',
  warning: 'text-[var(--color-warning-text)]',
  danger: 'text-[var(--color-danger-text)]',
  neutral: 'text-gray-500',
}

// Altura mínima de 20px, mesmo piso já adotado em `BarList` — o diagnóstico
// do projeto apontou que barras de 6-8px lêem como decoração, não dado.
const BAR_HEIGHT_CLASS = 'h-5'

function formatSignedPercent(deviationPercent: number): string {
  const rounded = Math.round(deviationPercent * 10) / 10
  const sign = rounded > 0 ? '+' : ''
  return `${sign}${rounded.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`
}

/**
 * Bullet chart (padrão Stephen Few) em SVG/CSS puro: compara um valor real
 * (`value`, barra preenchida) contra uma meta/referência (`target`, tick
 * vertical), sobre uma única escala com eixo legível (extremos 0 e `max`
 * rotulados abaixo da barra).
 *
 * `target: null` representa ausência de meta (ex.: produção esperada ainda
 * não disponível para a usina — ver `ExpectedDailyProduction`) — desenha só
 * a barra do valor real, sem tick e sem desvio calculado. Nunca fabrica uma
 * meta a partir de um dado ausente (mesmo princípio de `BarList` para
 * `value: null`).
 */
export function Bullet({
  value,
  target,
  max,
  label,
  valueFormatter,
  targetLabel = 'esperado',
  tone = 'neutral',
  className = '',
}: {
  value: number
  target: number | null
  // Escala do gráfico (extremo direito do eixo). Se ausente, usa 20% de folga
  // acima do maior entre `value` e `target` — nunca 0, para sempre haver uma
  // escala desenhável mesmo quando `value`/`target` são 0.
  max?: number
  label?: string
  valueFormatter?: (value: number) => string
  // Rótulo do tick de meta no texto acessível (ex.: "esperado", "meta",
  // "orçado") — permite reusar o componente fora do contexto de produção
  // fotovoltaica sem hardcodar o vocabulário.
  targetLabel?: string
  tone?: ChartTone
  className?: string
}) {
  const formatValue = valueFormatter ?? ((n: number) => String(n))
  const safeValue = Number.isFinite(value) ? value : 0
  const safeTarget = target != null && Number.isFinite(target) ? target : null

  const naturalMax = Math.max(safeValue, safeTarget ?? 0) * 1.2
  const effectiveMax = max != null && max > 0 ? max : naturalMax > 0 ? naturalMax : 1

  const valuePct = Math.min(Math.max((safeValue / effectiveMax) * 100, 0), 100)
  const targetPct =
    safeTarget != null ? Math.min(Math.max((safeTarget / effectiveMax) * 100, 0), 100) : null

  const deviationPercent =
    safeTarget != null && safeTarget !== 0 ? ((safeValue - safeTarget) / safeTarget) * 100 : null

  const color = TONE_BG_VAR[tone]

  // Animação de entrada (uma vez por montagem, nunca em refetch — ver
  // `useChartEntrance`): só a barra do valor real cresce de 0% até
  // `valuePct` — o tick de meta é uma referência estática, não uma medida
  // que "cresce", então aparece direto na posição final. `aria-label`/os
  // números abaixo da barra nunca dependem disto.
  const entered = useChartEntrance()

  const ariaLabel = (() => {
    const prefix = label ? `${label}: ` : ''
    const valueText = formatValue(safeValue)
    if (safeTarget == null) return `${prefix}${valueText}`
    const targetText = formatValue(safeTarget)
    if (deviationPercent == null) return `${prefix}${valueText}, ${targetLabel} ${targetText}`
    const direction = deviationPercent >= 0 ? 'acima' : 'abaixo'
    const magnitude = Math.abs(Math.round(deviationPercent * 10) / 10).toLocaleString('pt-BR', {
      maximumFractionDigits: 1,
    })
    return `${prefix}${valueText}, ${targetLabel} ${targetText} — ${magnitude}% ${direction} do esperado`
  })()

  return (
    <div className={`flex flex-col gap-1 ${className}`.trim()}>
      {label && (
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</span>
      )}
      <div
        role="img"
        aria-label={ariaLabel}
        className={`relative w-full overflow-hidden rounded-md bg-[var(--color-chart-track)] ${BAR_HEIGHT_CLASS}`}
      >
        <div
          className="h-full rounded-md transition-[width] duration-150 motion-reduce:transition-none"
          style={{ width: `${entered ? valuePct : 0}%`, backgroundColor: color }}
        />
        {targetPct != null && (
          <div
            className="absolute top-0 h-full w-0.5"
            style={{ left: `${targetPct}%`, backgroundColor: TARGET_TICK_COLOR }}
            data-testid="bullet-target-tick"
            aria-hidden="true"
          />
        )}
      </div>
      <div className="flex items-center justify-between text-[11px] text-gray-500 tabular-nums" aria-hidden="true">
        <span>0</span>
        <span>{formatValue(effectiveMax)}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm" aria-hidden="true">
        <span className="font-semibold tabular-nums text-[var(--color-text-primary)]">
          {formatValue(safeValue)}
        </span>
        {safeTarget != null && (
          <span className="text-gray-500 tabular-nums">
            {targetLabel} {formatValue(safeTarget)}
          </span>
        )}
        {deviationPercent != null && (
          <span className={`font-semibold tabular-nums ${DEVIATION_TONE_CLASS[tone]}`}>
            {formatSignedPercent(deviationPercent)}
          </span>
        )}
      </div>
    </div>
  )
}
