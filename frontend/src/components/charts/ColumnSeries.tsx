import type { ChartTone } from './Gauge'
import type { BarListItem } from './BarList'

// Mesmo shape de item de `BarList` (label/value/tone/badge/description/
// unavailableLabel) — reaproveitado em vez de duplicado (ver skill
// `chart-standards`: "não duplicar lógica de primitiva já existente"). O que
// muda entre as duas primitivas é só a orientação/eixo do desenho, não o
// contrato de dado de entrada.
export type ColumnSeriesItem = BarListItem

const TONE_BG_VAR: Record<ChartTone, string> = {
  success: 'var(--color-success-text)',
  warning: 'var(--color-warning-text)',
  danger: 'var(--color-danger-text)',
  neutral: 'var(--color-brand-primary)',
}

// Mesma paleta de selo (chip) usada em `BarList`, duplicada aqui pelo mesmo
// motivo (cada primitiva de `charts/` é autocontida, ver convenção já
// estabelecida nos outros arquivos deste diretório).
const BADGE_CLASS: Record<ChartTone, string> = {
  success: 'bg-[var(--color-success-light)] text-[var(--color-success-text)]',
  warning: 'bg-[var(--color-warning-light)] text-[var(--color-warning-text)]',
  danger: 'bg-[var(--color-danger-light)] text-[var(--color-danger-text)]',
  neutral: 'bg-gray-100 text-gray-600',
}

// Altura da área de colunas — grande o bastante para o eixo Y (0/metade/
// máximo) ser legível (skill `chart-standards`: "todo gráfico com grandeza
// numérica real precisa de eixo/escala legível"), mas bem mais compacta que
// os ~420px que a lista horizontal antiga ocupava para os mesmos 12 itens.
const CHART_HEIGHT = 160

// Altura fixa do marcador tracejado de "sem dado" — nunca proporcional a um
// valor ausente (mesmo princípio de `BarList` para `value: null`: um item
// sem dado nunca vira uma coluna de altura calculada, que seria lida como
// "produção baixa medida" em vez de "não medido").
const NO_DATA_MARKER_HEIGHT = 14

// Largura mínima de coluna — espaço suficiente para o rótulo do eixo X, o
// valor e o selo de qualidade (quando presente) sem colapsar em telas
// estreitas com muitos itens.
const MIN_COLUMN_WIDTH = 40

/**
 * Série de colunas verticais ao longo de um eixo de tempo/categoria, em
 * SVG/CSS puro (sem biblioteca de gráficos — ver skill `chart-standards`).
 *
 * Ao contrário de `BarList` (proporção entre itens, sem leitura cronológica
 * necessária), aqui a ordem esquerda→direita É o eixo do tempo — por isso um
 * eixo Y compartilhado (0/metade/máximo, sempre com a unidade de
 * `valueFormatter`) e rótulos de categoria por coluna, em vez de uma lista
 * empilhada de barras horizontais.
 *
 * `value: null` nunca vira coluna de altura zero (mesmo princípio de
 * `BarList`): desenha um marcador tracejado de altura fixa e baixa — lê como
 * "sem dado", nunca como "produção muito baixa".
 *
 * `badge`/`description` por item preservam sinalização de qualidade (ex.:
 * selo "dados parciais" + contagem exata de dias sem telemetria) sem
 * depender só de cor: a coluna sinalizada ganha contorno tracejado (pista
 * visual de forma, não só de cor — ver skill `accessible-charts`), o selo
 * permanece como chip visível abaixo da coluna, e a tabela `sr-only` no
 * final expõe o mesmo dado de forma estruturada para leitor de tela.
 */
export function ColumnSeries({
  items,
  maxValue,
  valueFormatter,
  legend,
  className = '',
}: {
  items: ColumnSeriesItem[]
  maxValue?: number
  valueFormatter?: (value: number) => string
  // Entradas de legenda (ex.: explicação do selo "dados parciais") exibidas
  // abaixo do gráfico — nunca só a cor/traço tracejado da coluna comunica o
  // significado (skill `accessible-charts`, regra 3).
  legend?: { label: string; tone: ChartTone; dashed?: boolean }[]
  className?: string
}) {
  if (items.length === 0) {
    return <p className={`text-sm text-gray-500 ${className}`.trim()}>Nenhum dado para exibir.</p>
  }

  const formatValue = valueFormatter ?? ((value: number) => String(value))
  const assessableValues = items
    .map((item) => item.value)
    .filter((value): value is number => value != null)
  const effectiveMax = maxValue ?? (assessableValues.length > 0 ? Math.max(...assessableValues) : 0)

  // Equivalente textual completo do gráfico inteiro — usado no `aria-label`
  // do `role="img"` que envolve só a área visual (barras), mesmo padrão de
  // `StackedBar`/`SankeyFlow`. Inclui o selo de qualidade quando presente,
  // para o estado "dados parciais" ser verificável via `aria-label`, não só
  // visualmente (ver instrução da tarefa).
  const ariaLabel = items
    .map((item) => {
      if (item.value == null) return `${item.label}: ${item.unavailableLabel ?? 'sem dado'}`
      const gapNote = item.badge ? `, ${item.badge.label}` : ''
      return `${item.label}: ${formatValue(item.value)}${gapNote}`
    })
    .join('; ')

  return (
    <div className={className}>
      {/* `data-testid`: o mesmo rótulo/valor aparece de novo, de propósito,
          na tabela `sr-only` abaixo (redundância intencional para leitor de
          tela — ver comentário da tabela) — sem um seletor próprio para a
          parte visual, `getByText` ficaria ambíguo entre as duas cópias em
          qualquer teste (mesmo padrão de `data-testid="bullet-target-tick"`
          em `Bullet.tsx`). */}
      <div className="flex items-stretch gap-2" data-testid="column-series-visual">
        {/* Eixo Y (0/metade/máximo), sempre com a mesma unidade de
            `valueFormatter` — decorativo/redundante com o `aria-label` e a
            tabela abaixo, por isso `aria-hidden`. */}
        <div
          className="flex flex-shrink-0 flex-col justify-between text-right text-xs text-gray-500 tabular-nums"
          style={{ height: CHART_HEIGHT }}
          aria-hidden="true"
        >
          <span>{formatValue(effectiveMax)}</span>
          <span>{formatValue(effectiveMax / 2)}</span>
          <span>{formatValue(0)}</span>
        </div>

        <div className="min-w-0 flex-1">
          <div role="img" aria-label={ariaLabel} className="relative" style={{ height: CHART_HEIGHT }}>
            <span
              className="pointer-events-none absolute inset-x-0 top-0 border-t border-gray-100"
              aria-hidden="true"
            />
            <span
              className="pointer-events-none absolute inset-x-0 border-t border-gray-100"
              style={{ top: '50%' }}
              aria-hidden="true"
            />
            <span
              className="pointer-events-none absolute inset-x-0 bottom-0 border-t border-gray-100"
              aria-hidden="true"
            />

            <div className="flex h-full items-end gap-2" aria-hidden="true">
              {items.map((item, index) => {
                if (item.value == null) {
                  return (
                    <div
                      key={`${item.label}-${index}`}
                      className="flex h-full flex-1 flex-col items-center justify-end"
                      style={{ minWidth: MIN_COLUMN_WIDTH }}
                    >
                      <div
                        className="w-full rounded-t-sm border-2 border-dashed border-[var(--color-chart-track)]"
                        style={{ height: NO_DATA_MARKER_HEIGHT }}
                      />
                    </div>
                  )
                }

                const pct =
                  effectiveMax > 0 ? Math.min(Math.max((item.value / effectiveMax) * 100, 0), 100) : 0
                const barHeight = Math.max((pct / 100) * CHART_HEIGHT, 3)
                const color = TONE_BG_VAR[item.tone ?? 'neutral']
                const badgeTone = item.badge?.tone

                return (
                  <div
                    key={`${item.label}-${index}`}
                    className="flex h-full flex-1 flex-col items-center justify-end"
                    style={{ minWidth: MIN_COLUMN_WIDTH }}
                  >
                    {/* `data-quality`: mesma informação do contorno tracejado,
                        como atributo — verificável em teste sem depender de
                        classe CSS/cor (ver instrução da tarefa). */}
                    <div
                      data-quality={badgeTone ? 'partial' : 'complete'}
                      className={`w-full rounded-t-sm transition-[height] duration-150 ${
                        badgeTone ? 'border-2 border-dashed' : ''
                      }`}
                      style={{
                        height: barHeight,
                        backgroundColor: color,
                        ...(badgeTone ? { borderColor: TONE_BG_VAR[badgeTone] } : {}),
                      }}
                    />
                  </div>
                )
              })}
            </div>
          </div>

          {/* Rótulos do eixo X + valor + selo de qualidade por coluna — texto
              real (não `aria-hidden`), mesmo tratamento que `BarList` já dava
              ao rótulo/selo de cada item: acessível pela leitura normal do
              DOM, além do resumo já coberto pelo `aria-label` acima e pela
              tabela `sr-only` abaixo. */}
          <div className="mt-1.5 flex gap-2">
            {items.map((item, index) => (
              <div
                key={`${item.label}-label-${index}`}
                className="flex flex-1 flex-col items-center gap-0.5 text-center"
                style={{ minWidth: MIN_COLUMN_WIDTH }}
              >
                <span className="text-xs text-gray-600" title={item.label}>
                  {item.label}
                </span>
                <span className="text-xs font-semibold tabular-nums text-[var(--color-text-primary)]">
                  {item.value == null ? item.unavailableLabel ?? '—' : formatValue(item.value)}
                </span>
                {item.badge && (
                  <span
                    className={`inline-block rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-tight ${BADGE_CLASS[item.badge.tone]}`}
                  >
                    {item.badge.label}
                  </span>
                )}
                {item.description && (
                  <span className="text-[10px] leading-tight text-gray-500">{item.description}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {legend && legend.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-gray-500" aria-hidden="true">
          {legend.map((entry, index) => (
            <li key={`${entry.label}-legend-${index}`} className="flex items-center gap-1.5">
              <span
                className={`inline-block h-2.5 w-2.5 shrink-0 rounded-sm ${
                  entry.dashed ? 'border-2 border-dashed bg-transparent' : ''
                }`}
                style={
                  entry.dashed
                    ? { borderColor: TONE_BG_VAR[entry.tone] }
                    : { backgroundColor: TONE_BG_VAR[entry.tone] }
                }
              />
              {entry.label}
            </li>
          ))}
        </ul>
      )}

      {/* Alternativa tabular equivalente para leitor de tela que prefira
          navegar os dados como tabela em vez de prosa no `aria-label` (mesmo
          padrão de `SankeyFlow`) — inclui a contagem exata de dias sem dado
          de `description`, que nunca aparece só em tooltip. */}
      <table className="sr-only">
        <caption>Valor e qualidade dos dados por item da série</caption>
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col">Valor</th>
            <th scope="col">Qualidade dos dados</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => (
            <tr key={`${item.label}-row-${index}`}>
              <th scope="row">{item.label}</th>
              <td>{item.value == null ? item.unavailableLabel ?? 'sem dado' : formatValue(item.value)}</td>
              <td>
                {item.badge ? item.badge.label : 'completo'}
                {item.description ? ` — ${item.description}` : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
