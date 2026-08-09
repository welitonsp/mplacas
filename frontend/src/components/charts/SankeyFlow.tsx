import type { ChartTone } from './Gauge'
import { useChartEntrance } from './useChartEntrance'

// A topologia de fluxo do Mplacas é fixa: produção → consumo (autoconsumo
// direto), produção → rede (injeção) e rede → consumo (importação). Este não
// é um Sankey genérico de layout dinâmico (não usa `d3-sankey` nem qualquer
// biblioteca — ver `chart-standards`), então os três nós têm ids conhecidos
// e coordenadas fixas no SVG.
export type SankeyNodeId = 'production' | 'grid' | 'consumption'

export type SankeyNode = {
  id: SankeyNodeId
  label: string
  value: number
}

export type SankeyLink = {
  from: SankeyNodeId
  to: SankeyNodeId
  value: number
  tone?: ChartTone
}

const TONE_STROKE_VAR: Record<ChartTone, string> = {
  success: 'var(--color-success-text)',
  warning: 'var(--color-warning-text)',
  danger: 'var(--color-danger-text)',
  neutral: 'var(--color-brand-primary)',
}

// Espessura mínima ainda perceptível como traço de dado real (mesmo
// princípio do piso de 16-20px de altura de barra em `BarList`/`Bullet`,
// adaptado a um traço de linha em vez de uma barra preenchida).
const MIN_STROKE = 4
const MAX_STROKE = 26

const VIEW_WIDTH = 600
const VIEW_HEIGHT = 260

// Atraso entre o início do traçado de cada fluxo (80-100ms dá a sensação de
// sequência — produção -> consumo, produção -> rede, rede -> consumo — em
// vez de tudo aparecendo simultaneamente).
const FLOW_STAGGER_MS = 90

// Caixas dos três nós, fixas porque a topologia é fixa (ver comentário do
// tipo `SankeyNodeId` acima). Produção à esquerda, Consumo à direita, Rede
// embaixo no meio — o autoconsumo flui direto de Produção a Consumo por
// cima, sem passar visualmente pela Rede.
const NODE_BOX: Record<SankeyNodeId, { x: number; y: number; width: number; height: number }> = {
  production: { x: 12, y: 88, width: 150, height: 64 },
  grid: { x: 225, y: 182, width: 150, height: 64 },
  consumption: { x: 438, y: 88, width: 150, height: 64 },
}

// Pontos de ancoragem de cada traço na borda dos nós, também fixos pela
// mesma razão. Cada nó tem até dois pontos de saída/entrada (produção
// alimenta dois fluxos, consumo recebe dois) para os traços não se
// sobreporem visualmente na borda do retângulo.
const ANCHORS = {
  productionToConsumption: { start: { x: 162, y: 108 }, end: { x: 438, y: 108 } },
  productionToGrid: { start: { x: 162, y: 132 }, end: { x: 260, y: 182 } },
  gridToConsumption: { start: { x: 340, y: 182 }, end: { x: 438, y: 132 } },
} as const

function flowKey(from: SankeyNodeId, to: SankeyNodeId): keyof typeof ANCHORS | null {
  if (from === 'production' && to === 'consumption') return 'productionToConsumption'
  if (from === 'production' && to === 'grid') return 'productionToGrid'
  if (from === 'grid' && to === 'consumption') return 'gridToConsumption'
  return null
}

function pathFor(key: keyof typeof ANCHORS): string {
  const { start, end } = ANCHORS[key]
  const midX = (start.x + end.x) / 2
  return `M ${start.x} ${start.y} C ${midX} ${start.y} ${midX} ${end.y} ${end.x} ${end.y}`
}

/**
 * Diagrama de fluxo de energia (produção → autoconsumo/injeção, rede →
 * importação) em SVG puro, sem biblioteca de Sankey — a topologia é sempre a
 * mesma três nós, então três `<path>` de Bézier cúbica fixos resolvem sem a
 * generalização de um Sankey de layout dinâmico.
 *
 * A espessura de cada traço é proporcional ao seu `value` (kWh) relativo ao
 * maior fluxo renderizável. Fluxo com `value <= 0` não é desenhado (nunca um
 * traço de espessura zero forçado, mesmo princípio de `StackedBar` para
 * segmento zero).
 */
export function SankeyFlow({
  nodes,
  flows,
  valueFormatter,
  className = '',
}: {
  nodes: SankeyNode[]
  flows: SankeyLink[]
  valueFormatter?: (value: number) => string
  className?: string
}) {
  const formatValue = valueFormatter ?? ((value: number) => String(value))

  // Animação de entrada (uma vez por montagem, nunca em refetch — ver
  // `useChartEntrance`): cada `<path>` é "desenhado" do início ao fim via
  // `pathLength`/`stroke-dashoffset` (técnica clássica de traçado SVG — o
  // atributo `pathLength={1}` normaliza o comprimento de QUALQUER path para
  // 1 unidade, então `stroke-dasharray={1}` + `stroke-dashoffset` indo de 1
  // [invisível] a 0 [completo] funciona sem medir o comprimento real do
  // traço em pixels, suportado nativamente pelo navegador — nenhuma
  // dependência nova). `aria-label`/a tabela `sr-only` nunca dependem disto.
  const entered = useChartEntrance()

  if (nodes.length === 0) {
    return <p className={`text-sm text-gray-500 ${className}`.trim()}>Nenhum dado para exibir.</p>
  }

  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const renderableFlows = flows.filter((flow) => flow.value > 0 && flowKey(flow.from, flow.to) != null)
  const maxFlowValue = renderableFlows.reduce((max, flow) => Math.max(max, flow.value), 0)

  const strokeWidthFor = (value: number): number => {
    if (maxFlowValue <= 0) return MIN_STROKE
    const ratio = value / maxFlowValue
    return MIN_STROKE + ratio * (MAX_STROKE - MIN_STROKE)
  }

  const production = nodeById.get('production')
  const consumption = nodeById.get('consumption')
  const autoFlow = flows.find((flow) => flow.from === 'production' && flow.to === 'consumption')
  const injectionFlow = flows.find((flow) => flow.from === 'production' && flow.to === 'grid')
  const importFlow = flows.find((flow) => flow.from === 'grid' && flow.to === 'consumption')

  const ariaLabel = (() => {
    const sentences: string[] = []
    if (production) {
      const parts: string[] = []
      if (autoFlow && autoFlow.value > 0) {
        parts.push(`${formatValue(autoFlow.value)} consumidos diretamente`)
      }
      if (injectionFlow && injectionFlow.value > 0) {
        parts.push(`${formatValue(injectionFlow.value)} injetados na rede`)
      }
      sentences.push(
        `${production.label} de ${formatValue(production.value)}${parts.length ? `: ${parts.join(', ')}` : ''}`,
      )
    }
    if (consumption) {
      const parts: string[] = []
      if (autoFlow && autoFlow.value > 0) {
        parts.push(`${formatValue(autoFlow.value)} de produção própria`)
      }
      if (importFlow && importFlow.value > 0) {
        parts.push(`${formatValue(importFlow.value)} importados da rede`)
      }
      sentences.push(
        `${consumption.label} total de ${formatValue(consumption.value)}${parts.length ? `: ${parts.join(', ')}` : ''}`,
      )
    }
    return sentences.length > 0 ? `${sentences.join('. ')}.` : ''
  })()

  return (
    <div className={className}>
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        role="img"
        aria-label={ariaLabel}
        className="w-full h-auto"
      >
        {renderableFlows.map((flow, index) => {
          const key = flowKey(flow.from, flow.to)
          if (!key) return null
          const color = TONE_STROKE_VAR[flow.tone ?? 'neutral']
          return (
            <path
              key={`${flow.from}-${flow.to}-${index}`}
              d={pathFor(key)}
              fill="none"
              stroke={color}
              strokeWidth={strokeWidthFor(flow.value)}
              strokeLinecap="round"
              opacity={0.85}
              aria-hidden="true"
              pathLength={1}
              strokeDasharray={1}
              strokeDashoffset={entered ? 0 : 1}
              className="transition-[stroke-dashoffset] duration-500 motion-reduce:transition-none"
              style={{ transitionDelay: `${index * FLOW_STAGGER_MS}ms` }}
            />
          )
        })}

        {nodes.map((node) => {
          const box = NODE_BOX[node.id]
          if (!box) return null
          return (
            <g key={node.id} aria-hidden="true">
              <rect
                x={box.x}
                y={box.y}
                width={box.width}
                height={box.height}
                rx={8}
                fill="var(--color-surface)"
                stroke="var(--color-border)"
                strokeWidth={1}
              />
              <text
                x={box.x + box.width / 2}
                y={box.y + 24}
                textAnchor="middle"
                className="fill-gray-500"
                style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em' }}
              >
                {node.label}
              </text>
              <text
                x={box.x + box.width / 2}
                y={box.y + 44}
                textAnchor="middle"
                className="fill-gray-900"
                style={{ fontSize: 16, fontWeight: 600 }}
              >
                {formatValue(node.value)}
              </text>
            </g>
          )
        })}
      </svg>

      {/* Alternativa tabular equivalente para leitor de tela que não navega
          bem um SVG complexo com múltiplos traços sobrepostos (ver skill
          `accessible-charts`). */}
      <table className="sr-only">
        <caption>Fluxo de energia: valores por nó e por fluxo</caption>
        <thead>
          <tr>
            <th scope="col">Nó</th>
            <th scope="col">Valor</th>
          </tr>
        </thead>
        <tbody>
          {nodes.map((node) => (
            <tr key={node.id}>
              <th scope="row">{node.label}</th>
              <td>{formatValue(node.value)}</td>
            </tr>
          ))}
          {flows.map((flow, index) => {
            const from = nodeById.get(flow.from)?.label ?? flow.from
            const to = nodeById.get(flow.to)?.label ?? flow.to
            return (
              <tr key={`${flow.from}-${flow.to}-flow-${index}`}>
                <th scope="row">
                  {from} → {to}
                </th>
                <td>{formatValue(flow.value)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
