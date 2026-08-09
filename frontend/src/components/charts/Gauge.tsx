import { clampPercent } from '../../lib/format'
import { useChartEntrance } from './useChartEntrance'

export type ChartTone = 'success' | 'warning' | 'danger' | 'neutral'

// Mapeamento de tom -> token de cor semântico já existente no projeto (ver
// `frontend/src/index.css`). Nunca inventar cor nova aqui — reforça a
// convenção de severidade usada em `Card`/`MetricCard`.
const TONE_COLOR_VAR: Record<ChartTone, string> = {
  success: 'var(--color-success-text)',
  warning: 'var(--color-warning-text)',
  danger: 'var(--color-danger-text)',
  neutral: 'var(--color-brand-primary)',
}

// Circunferência de um círculo com r=15.9155 em um viewBox 36x36 é ~100,
// o que permite usar `strokeDasharray` diretamente em unidades percentuais
// (0-100) sem nenhuma conta extra de perímetro.
const RADIUS = 15.9155

// O texto central escala com `size` para não ficar minúsculo em gauges
// grandes (ex: HeroCard, 112px — o índice de saúde da usina, o número mais
// importante da tela) nem estourar o círculo em gauges pequenos (ex:
// PerformanceRatioCard/ReportingAvailabilityCard, 72px). Faixas cobrem os
// tamanhos em uso hoje no projeto (72, 96 default, 112) com folga para
// tamanhos intermediários futuros, sem depender de cálculo proporcional
// que exigiria font-size arbitrário fora da escala do Tailwind.
function centerTextClass(size: number): string {
  if (size >= 104) return 'text-xl'
  if (size >= 84) return 'text-sm'
  return 'text-xs'
}

/**
 * Anel de progresso (gauge) circular em SVG puro, sem dependência de
 * biblioteca de gráficos.
 *
 * `value` é sempre 0-100 (percentual) e é clampado para esse intervalo antes
 * de desenhar, para nunca produzir um `strokeDasharray` inválido. `valueLabel`
 * é o texto exibido no centro (ex: "82%", "8,2h") — desacoplado de `value`
 * para permitir formatação livre (ex: unidades diferentes de percentual).
 */
export function Gauge({
  value,
  label,
  valueLabel,
  size = 96,
  tone = 'neutral',
  className = '',
}: {
  value: number
  label?: string
  valueLabel?: string
  size?: number
  tone?: ChartTone
  className?: string
}) {
  const pct = clampPercent(value)
  const displayValue = valueLabel ?? `${Math.round(pct)}%`
  const ariaLabel = label ? `${label}: ${displayValue}` : `${displayValue} de 100`
  const color = TONE_COLOR_VAR[tone]

  // Animação de entrada (uma vez por montagem, nunca em refetch — ver
  // `useChartEntrance`): o anel cresce de 0 até `pct`. `displayValue`/
  // `ariaLabel` acima NUNCA dependem disto — o texto/rótulo acessível
  // sempre mostra o valor real desde o primeiro render, só o traço visual
  // do SVG começa vazio.
  const entered = useChartEntrance()
  const drawnPct = entered ? pct : 0

  return (
    <div
      className={`relative inline-flex flex-col items-center ${className}`.trim()}
      style={{ width: size }}
    >
      <svg viewBox="0 0 36 36" width={size} height={size} role="img" aria-label={ariaLabel}>
        <circle
          cx="18"
          cy="18"
          r={RADIUS}
          fill="none"
          stroke="var(--color-chart-track)"
          strokeWidth="3"
        />
        <circle
          cx="18"
          cy="18"
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={`${drawnPct} 100`}
          transform="rotate(-90 18 18)"
          className="transition-[stroke-dasharray] duration-150 motion-reduce:transition-none"
        />
      </svg>
      <div
        className={`pointer-events-none absolute inset-0 flex items-center justify-center font-semibold tabular-nums text-[var(--color-text-primary)] ${centerTextClass(size)}`}
        aria-hidden="true"
      >
        {displayValue}
      </div>
      {label && (
        <p className="mt-1 text-center text-xs font-medium text-gray-500 uppercase tracking-wide">
          {label}
        </p>
      )}
    </div>
  )
}
