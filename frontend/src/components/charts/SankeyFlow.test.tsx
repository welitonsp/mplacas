import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { stubMatchMediaMatches } from '../../test/matchMedia'
import { SankeyFlow } from './SankeyFlow'

afterEach(() => {
  vi.unstubAllGlobals()
})

const baseNodes = [
  { id: 'production' as const, label: 'Produção', value: 543.6 },
  { id: 'grid' as const, label: 'Rede', value: 0 },
  { id: 'consumption' as const, label: 'Consumo', value: 543.6 },
]

describe('SankeyFlow', () => {
  it('desenha um <path> por fluxo com espessura proporcional ao valor', () => {
    render(
      <SankeyFlow
        nodes={baseNodes}
        flows={[
          { from: 'production', to: 'consumption', value: 278.6 },
          { from: 'production', to: 'grid', value: 265 },
          { from: 'grid', to: 'consumption', value: 265 },
        ]}
        valueFormatter={(v) => `${v} kWh`}
      />,
    )

    const svg = screen.getByRole('img')
    const paths = svg.querySelectorAll('path')
    expect(paths).toHaveLength(3)

    const widths = Array.from(paths).map((path) => Number(path.getAttribute('stroke-width')))
    // O maior fluxo (278.6) deve ter o traço mais espesso.
    expect(widths[0]).toBeGreaterThan(widths[1])
    expect(widths[1]).toBe(widths[2])
  })

  it('não desenha fluxo com valor 0 ou negativo', () => {
    render(
      <SankeyFlow
        nodes={baseNodes}
        flows={[
          { from: 'production', to: 'consumption', value: 278.6 },
          { from: 'production', to: 'grid', value: 0 },
          { from: 'grid', to: 'consumption', value: -5 },
        ]}
      />,
    )

    const svg = screen.getByRole('img')
    expect(svg.querySelectorAll('path')).toHaveLength(1)
  })

  it('expõe aria-label textual resumindo produção e consumo', () => {
    render(
      <SankeyFlow
        nodes={baseNodes}
        flows={[
          { from: 'production', to: 'consumption', value: 278.6 },
          { from: 'production', to: 'grid', value: 265 },
          { from: 'grid', to: 'consumption', value: 265 },
        ]}
        valueFormatter={(v) => `${v.toLocaleString('pt-BR')} kWh`}
      />,
    )

    const svg = screen.getByRole('img')
    expect(svg).toHaveAttribute(
      'aria-label',
      'Produção de 543,6 kWh: 278,6 kWh consumidos diretamente, 265 kWh injetados na rede. Consumo total de 543,6 kWh: 278,6 kWh de produção própria, 265 kWh importados da rede.',
    )
  })

  it('expõe tabela sr-only com os valores de nós e fluxos', () => {
    render(
      <SankeyFlow
        nodes={baseNodes}
        flows={[
          { from: 'production', to: 'consumption', value: 278.6 },
          { from: 'production', to: 'grid', value: 265 },
          { from: 'grid', to: 'consumption', value: 265 },
        ]}
        valueFormatter={(v) => `${v} kWh`}
      />,
    )

    const table = document.querySelector('table.sr-only')
    expect(table).toBeInTheDocument()
    expect(table).toHaveTextContent('Produção')
    expect(table).toHaveTextContent('543.6 kWh')
    expect(table).toHaveTextContent('Rede')
    expect(table).toHaveTextContent('Consumo')
    expect(table).toHaveTextContent('278.6 kWh')
  })

  it('não quebra e mostra mensagem quando não há nós', () => {
    render(<SankeyFlow nodes={[]} flows={[]} />)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('Nenhum dado para exibir.')).toBeInTheDocument()
  })

  describe('traçado de entrada (uma vez por montagem, nunca em refetch)', () => {
    const flows = [
      { from: 'production' as const, to: 'consumption' as const, value: 278.6 },
      { from: 'production' as const, to: 'grid' as const, value: 265 },
      { from: 'grid' as const, to: 'consumption' as const, value: 265 },
    ]

    it('cada <path> nasce invisível (dashoffset 1) e "desenha" até completo (dashoffset 0) após a montagem, escalonado por índice', async () => {
      render(<SankeyFlow nodes={baseNodes} flows={flows} />)

      const paths = screen.getByRole('img').querySelectorAll('path')
      expect(paths).toHaveLength(3)

      paths.forEach((path) => {
        expect(path).toHaveAttribute('stroke-dashoffset', '1')
        expect(path).toHaveAttribute('pathLength', '1')
      })
      // Atraso escalonado (índice * 90ms) — cada traço começa a desenhar em
      // um instante diferente, nunca todos simultaneamente.
      expect((paths[0] as SVGPathElement).style.transitionDelay).toBe('0ms')
      expect((paths[1] as SVGPathElement).style.transitionDelay).toBe('90ms')
      expect((paths[2] as SVGPathElement).style.transitionDelay).toBe('180ms')

      await waitFor(() => {
        paths.forEach((path) => {
          expect(path).toHaveAttribute('stroke-dashoffset', '0')
        })
      })
    })

    it('prefers-reduced-motion: reduce mostra os traços completos já no primeiro render, sem animação', () => {
      stubMatchMediaMatches(true)

      render(<SankeyFlow nodes={baseNodes} flows={flows} />)

      const paths = screen.getByRole('img').querySelectorAll('path')
      paths.forEach((path) => {
        expect(path).toHaveAttribute('stroke-dashoffset', '0')
      })
    })

    it('um refetch (rerender com valores novos, sem desmontar) não reanima o traçado', async () => {
      const { rerender } = render(<SankeyFlow nodes={baseNodes} flows={flows} />)

      const getPaths = () => screen.getByRole('img').querySelectorAll('path')

      await waitFor(() => {
        getPaths().forEach((path) => expect(path).toHaveAttribute('stroke-dashoffset', '0'))
      })

      rerender(
        <SankeyFlow
          nodes={baseNodes}
          flows={[
            { from: 'production', to: 'consumption', value: 300 },
            { from: 'production', to: 'grid', value: 265 },
            { from: 'grid', to: 'consumption', value: 265 },
          ]}
        />,
      )

      getPaths().forEach((path) => expect(path).toHaveAttribute('stroke-dashoffset', '0'))
    })
  })
})
