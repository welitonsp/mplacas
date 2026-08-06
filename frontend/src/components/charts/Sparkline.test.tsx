import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Sparkline } from './Sparkline'

describe('Sparkline', () => {
  it('cresce para a direita do eixo central quando o delta é positivo', () => {
    render(<Sparkline percentDelta={12} label="Produção" />)

    const bar = screen.getByRole('img')
    const fill = bar.firstElementChild as HTMLElement
    expect(fill.style.left).toBe('50%')
    expect(Number.parseFloat(fill.style.width)).toBeGreaterThan(0)
  })

  it('cresce para a esquerda do eixo central quando o delta é negativo', () => {
    render(<Sparkline percentDelta={-12} label="Energia importada" />)

    const bar = screen.getByRole('img')
    const fill = bar.firstElementChild as HTMLElement
    const left = Number.parseFloat(fill.style.left)
    const width = Number.parseFloat(fill.style.width)

    expect(left).toBeLessThan(50)
    expect(left + width).toBeCloseTo(50, 5)
  })

  it('largura da barra é proporcional a maxAbsPercent explícito', () => {
    render(<Sparkline percentDelta={20} maxAbsPercent={40} label="Produção" />)

    const bar = screen.getByRole('img')
    const fill = bar.firstElementChild as HTMLElement
    // 20 / 40 * 50 = 25%
    expect(fill.style.width).toBe('25%')
  })

  it('nunca ultrapassa metade da largura mesmo quando o delta excede maxAbsPercent', () => {
    render(<Sparkline percentDelta={90} maxAbsPercent={40} label="Produção" />)

    const bar = screen.getByRole('img')
    const fill = bar.firstElementChild as HTMLElement
    expect(fill.style.width).toBe('50%')
  })

  it('expõe aria-label textual completo com direção por extenso, não só símbolo', () => {
    render(<Sparkline percentDelta={12} label="Produção" />)

    const bar = screen.getByRole('img')
    expect(bar).toHaveAttribute(
      'aria-label',
      'Produção: aumentou 12,0% em relação ao ciclo anterior',
    )
  })

  it('usa "diminuiu" no aria-label para delta negativo', () => {
    render(<Sparkline percentDelta={-3.4} label="Energia importada" />)

    const bar = screen.getByRole('img')
    expect(bar).toHaveAttribute(
      'aria-label',
      'Energia importada: diminuiu 3,4% em relação ao ciclo anterior',
    )
  })

  it('trata delta zero como estado explícito de "sem variação", sem barra fabricada', () => {
    render(<Sparkline percentDelta={0} label="Consumo total" />)

    const bar = screen.getByRole('img')
    expect(bar).toHaveAttribute(
      'aria-label',
      'Consumo total: sem variação em relação ao ciclo anterior',
    )
    // Nenhum elemento de preenchimento (só o eixo central) deve existir.
    expect(bar.children).toHaveLength(1)
  })

  it('trata delta null/indisponível como estado explícito, sem fabricar direção arbitrária', () => {
    render(<Sparkline percentDelta={null} label="Produção" />)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    const placeholder = screen.getByRole('status')
    expect(placeholder).toHaveAttribute(
      'aria-label',
      'Produção: variação percentual indisponível',
    )
  })

  it('usa valueFormatter customizado no aria-label quando informado', () => {
    render(
      <Sparkline
        percentDelta={5}
        label="Produção"
        valueFormatter={(n) => `${Math.abs(n).toFixed(2)} pp`}
      />,
    )

    const bar = screen.getByRole('img')
    expect(bar).toHaveAttribute(
      'aria-label',
      'Produção: aumentou 5.00 pp em relação ao ciclo anterior',
    )
  })
})
