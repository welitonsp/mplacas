import type { ChartTone } from './Gauge'
import { useChartEntrance } from './useChartEntrance'

export type BarListItem = {
  label: string
  // `null` representa um valor não avaliável/não aplicável (ex.: categoria de
  // perda cujo `evidence_level` é NOT_ASSESSABLE/NOT_DETECTED e o backend não
  // produziu uma estimativa numérica) — nunca deve ser tratado como 0, que
  // fabricaria uma barra preenchida sugerindo "perda medida zero". Itens com
  // `value: null` são desenhados como um estado neutro sem barra, mas mantêm
  // a posição original na lista (`BarList` nunca reordena, ver `Etapa 2`).
  value: number | null
  tone?: ChartTone
  unavailableLabel?: string
  // Selo opcional exibido abaixo do rótulo (ex.: nível de evidência de uma
  // categoria de perda) — mantém contexto qualitativo junto do item sem
  // sobrepor a barra/valor quantitativo.
  badge?: { label: string; tone: ChartTone }
  // Texto auxiliar opcional exibido abaixo do item inteiro (ex.: ressalva de
  // limitação de um item não avaliável).
  description?: string
}

const TONE_BG_VAR: Record<ChartTone, string> = {
  success: 'var(--color-success-text)',
  warning: 'var(--color-warning-text)',
  danger: 'var(--color-danger-text)',
  neutral: 'var(--color-brand-primary)',
}

// Selo (badge) opcional por item — mesma paleta clara/texto usada em outros
// pontos do dashboard para "chip" de severidade (ver `SEVERITY_BG`/
// `SEVERITY_TEXT` em `lib/dashboard/visuals.ts`; duplicado aqui como classes
// Tailwind porque `charts/` é um primitivo genérico, sem depender do módulo
// de domínio do dashboard).
const BADGE_CLASS: Record<ChartTone, string> = {
  success: 'bg-[var(--color-success-light)] text-[var(--color-success-text)]',
  warning: 'bg-[var(--color-warning-light)] text-[var(--color-warning-text)]',
  danger: 'bg-[var(--color-danger-light)] text-[var(--color-danger-text)]',
  neutral: 'bg-gray-100 text-gray-600',
}

// Altura mínima de 20px — o diagnóstico apontou que as barras de 6px do
// projeto eram ilegíveis/imperceptíveis. Não reduzir abaixo desse valor.
const BAR_HEIGHT_CLASS = 'h-5'

/**
 * Lista vertical de barras horizontais proporcionais, em SVG/CSS puro.
 *
 * A largura de cada barra é proporcional a `value` relativo a `maxValue`
 * (se informado) ou ao maior `value` presente em `items` (padrão, ignorando
 * itens com `value: null`). Valores negativos ou `maxValue` inválido (<= 0)
 * resultam em barra de largura 0, nunca em cálculo inválido. Itens com
 * `value: null` não desenham barra nenhuma (ver `BarListItem`).
 */
export function BarList({
  items,
  maxValue,
  valueFormatter,
  className = '',
}: {
  items: BarListItem[]
  maxValue?: number
  valueFormatter?: (value: number) => string
  className?: string
}) {
  if (items.length === 0) {
    return (
      <p className={`text-sm text-gray-500 ${className}`.trim()}>Nenhum dado para exibir.</p>
    )
  }

  const assessableValues = items
    .map((item) => item.value)
    .filter((value): value is number => value != null)
  const effectiveMax = maxValue ?? (assessableValues.length > 0 ? Math.max(...assessableValues) : 0)
  const formatValue = valueFormatter ?? ((value: number) => String(value))

  // Animação de entrada (uma vez por montagem, nunca em refetch — ver
  // `useChartEntrance`): cada barra cresce de 0% até sua largura real.
  // `aria-valuenow`/`aria-label`/o valor textual ao lado nunca dependem
  // disto — sempre mostram o valor real desde o primeiro render.
  const entered = useChartEntrance()

  return (
    <ul className={`flex flex-col gap-3 ${className}`.trim()}>
      {items.map((item, index) => {
        const color = TONE_BG_VAR[item.tone ?? 'neutral']

        const labelColumn = (
          <div className="w-28 shrink-0">
            <span className="block truncate text-sm text-gray-600" title={item.label}>
              {item.label}
            </span>
            {item.badge && (
              <span
                className={`mt-1 inline-block rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${BADGE_CLASS[item.badge.tone]}`}
              >
                {item.badge.label}
              </span>
            )}
          </div>
        )

        if (item.value == null) {
          const unavailableLabel = item.unavailableLabel ?? '—'
          return (
            <li key={`${item.label}-${index}`} className="flex flex-col gap-1">
              <div className="flex items-center gap-3">
                {labelColumn}
                <div
                  className={`relative flex-1 overflow-hidden rounded-md border border-dashed border-[var(--color-chart-track)] ${BAR_HEIGHT_CLASS}`}
                  role="status"
                  aria-label={`${item.label}: ${unavailableLabel}`}
                />
                <span className="w-16 shrink-0 text-right text-sm font-semibold tabular-nums text-gray-500">
                  {unavailableLabel}
                </span>
              </div>
              {item.description && (
                <p className="pl-[7.75rem] text-xs text-gray-500">{item.description}</p>
              )}
            </li>
          )
        }

        const pct =
          effectiveMax > 0 ? Math.min(Math.max((item.value / effectiveMax) * 100, 0), 100) : 0

        return (
          <li key={`${item.label}-${index}`} className="flex flex-col gap-1">
            <div className="flex items-center gap-3">
              {labelColumn}
              <div
                className={`relative flex-1 overflow-hidden rounded-md bg-[var(--color-chart-track)] ${BAR_HEIGHT_CLASS}`}
                role="progressbar"
                aria-valuenow={item.value}
                aria-valuemin={0}
                aria-valuemax={effectiveMax}
                aria-label={`${item.label}: ${formatValue(item.value)}`}
              >
                <div
                  className="h-full rounded-md transition-[width] duration-150 motion-reduce:transition-none"
                  style={{ width: `${entered ? pct : 0}%`, backgroundColor: color }}
                />
              </div>
              <span className="w-16 shrink-0 text-right text-sm font-semibold tabular-nums text-[var(--color-text-primary)]">
                {formatValue(item.value)}
              </span>
            </div>
            {item.description && <p className="pl-[7.75rem] text-xs text-gray-500">{item.description}</p>}
          </li>
        )
      })}
    </ul>
  )
}
