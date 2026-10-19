import { useEffect, useRef, useState } from 'react'
import { niceAxisMax } from './ColumnSeries'

// Duas linhas de patrimônio ao longo dos anos — usina (economias reinvestidas
// no CDI) × o mesmo investimento só no CDI (ADR-079). Primitiva SVG pura, sem
// biblioteca (skill `chart-standards`). Cores com papel fixo (ADR-077): verde
// = produção/usina; marinho-acinzentado de referência = CDI. Marca o ponto em
// que as linhas se cruzam, porque é a resposta que o investidor procura:
// "a partir de quando a usina passa o CDI?". Alternativa em tabela para
// leitor de tela, como nos outros gráficos do projeto.

export interface PatrimonyLinePoint {
  year: number
  cdi: number
  solar: number
}

// A largura do SVG acompanha a largura real do contêiner: com um viewBox fixo
// de 720, no celular de 360 px o texto de 12 encolhia para ~5 px (ilegível).
// Medindo, a fonte é sempre 12 px de verdade e só o traçado se adapta.
const DEFAULT_WIDTH = 720
const MIN_WIDTH = 280
const HEIGHT = 260
const TOP = 16
const BOTTOM = 36

function useMeasuredWidth() {
  const ref = useRef<HTMLElement | null>(null)
  const [width, setWidth] = useState(DEFAULT_WIDTH)
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      const measured = Math.round(entries[0]?.contentRect.width ?? 0)
      if (measured > 0) setWidth(Math.max(MIN_WIDTH, measured))
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return { ref, width }
}

function brlShort(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `R$ ${Math.round(value / 1000).toLocaleString('pt-BR')} mil`
  }
  return `R$ ${Math.round(value).toLocaleString('pt-BR')}`
}

/** Ano (fracionário) em que a usina passa o CDI, por interpolação; `null` se nunca. */
export function crossoverYear(points: PatrimonyLinePoint[]): number | null {
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1]
    const curr = points[i]
    const before = prev.solar - prev.cdi
    const after = curr.solar - curr.cdi
    if (before < 0 && after >= 0) {
      return prev.year + ((0 - before) / (after - before)) * (curr.year - prev.year)
    }
  }
  return null
}

export function PatrimonyLines({
  points,
  ariaLabel,
  crossover: crossoverOverride,
}: {
  points: PatrimonyLinePoint[]
  ariaLabel: string
  /**
   * Ano em que a usina passa o CDI, quando o backend já o calculou (payback
   * descontado, mês a mês). Prevalece sobre a interpolação entre pontos
   * anuais, que é grosseira. `null` = não passa no horizonte.
   */
  crossover?: number | null
}) {
  const { ref, width: WIDTH } = useMeasuredWidth()
  if (points.length < 2) return null
  const narrow = WIDTH < 480
  const LEFT = 72
  const RIGHT = narrow ? 48 : 96
  const lastYear = points[points.length - 1].year
  const max = niceAxisMax(Math.max(...points.map((p) => Math.max(p.cdi, p.solar))))
  const min = Math.min(0, ...points.map((p) => p.solar))
  const plotW = WIDTH - LEFT - RIGHT
  const plotH = HEIGHT - TOP - BOTTOM
  const x = (year: number) => LEFT + (year / lastYear) * plotW
  const y = (value: number) => TOP + plotH - ((value - min) / (max - min)) * plotH
  const path = (key: 'cdi' | 'solar') =>
    points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.year).toFixed(1)},${y(p[key]).toFixed(1)}`).join(' ')
  const ticks = [0, 1, 2, 3, 4].map((k) => min + ((max - min) * k) / 4)
  // No celular, rótulo a cada 10 anos: a cada 5 os textos se encavalavam.
  const yearStep = narrow ? 10 : 5
  const yearTicks = points.filter((p) => p.year % yearStep === 0).map((p) => p.year)
  const cross = crossoverOverride !== undefined ? crossoverOverride : crossoverYear(points)
  // Rótulo do cruzamento vira para a esquerda quando a linha está na metade
  // direita, para não vazar do gráfico.
  const crossLabelLeft = cross !== null && x(cross) > LEFT + plotW / 2
  const last = points[points.length - 1]

  return (
    <figure className="m-0" ref={ref}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={ariaLabel} className="h-auto w-full">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={LEFT} x2={LEFT + plotW} y1={y(tick)} y2={y(tick)} stroke="var(--color-chart-grid)" />
            <text x={LEFT - 8} y={y(tick) + 4} textAnchor="end" fontSize="12" fill="var(--color-text-secondary)">
              {brlShort(tick)}
            </text>
          </g>
        ))}
        {yearTicks.map((year) => (
          <text
            key={year}
            x={x(year)}
            y={HEIGHT - BOTTOM + 20}
            textAnchor="middle"
            fontSize="12"
            fill="var(--color-text-secondary)"
          >
            {year === 0 ? 'ligação' : `ano ${year}`}
          </text>
        ))}
        {cross !== null && (
          <g>
            <line
              x1={x(cross)}
              x2={x(cross)}
              y1={TOP}
              y2={TOP + plotH}
              stroke="var(--color-chart-reference)"
              strokeDasharray="4 4"
            />
            <text
              x={x(cross) + (crossLabelLeft ? -6 : 6)}
              y={TOP + 12}
              textAnchor={crossLabelLeft ? 'end' : 'start'}
              fontSize="12"
              fill="var(--color-text-secondary)"
            >
              {`${narrow ? 'passa o CDI' : 'usina passa o CDI'} ≈ ano ${cross.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}`}
            </text>
          </g>
        )}
        <path d={path('cdi')} fill="none" stroke="var(--color-chart-reference)" strokeWidth="2.5" />
        <path d={path('solar')} fill="none" stroke="var(--color-energy-solar)" strokeWidth="3" />
        <text x={x(last.year) + 6} y={y(last.solar) + 4} fontSize="12" fontWeight="600" fill="var(--color-text-primary)">
          Usina
        </text>
        <text x={x(last.year) + 6} y={y(last.cdi) + 4} fontSize="12" fill="var(--color-text-secondary)">
          CDI
        </text>
      </svg>
      {/* `sr-only` no invólucro, nunca direto na <table> (tabela ignora
          width: 1px e fazia a página rolar de lado no celular, ADR-077). */}
      <div className="sr-only">
      <table>
        <caption>{ariaLabel}</caption>
        <thead>
          <tr>
            <th scope="col">Ano</th>
            <th scope="col">Usina (economias no CDI)</th>
            <th scope="col">Só no CDI</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.year}>
              <td>{p.year}</td>
              <td>{brlShort(p.solar)}</td>
              <td>{brlShort(p.cdi)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </figure>
  )
}
