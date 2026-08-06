import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Gauge } from './Gauge'

describe('Gauge', () => {
  it('desenha strokeDasharray "0 100" quando value=0', () => {
    const { container } = render(<Gauge value={0} label="Índice de saúde" />)
    const progressCircle = container.querySelectorAll('circle')[1]

    expect(progressCircle).toHaveAttribute('stroke-dasharray', '0 100')
  })

  it('desenha strokeDasharray "50 100" quando value=50', () => {
    const { container } = render(<Gauge value={50} label="Índice de saúde" />)
    const progressCircle = container.querySelectorAll('circle')[1]

    expect(progressCircle).toHaveAttribute('stroke-dasharray', '50 100')
  })

  it('desenha strokeDasharray "100 100" quando value=100', () => {
    const { container } = render(<Gauge value={100} label="Índice de saúde" />)
    const progressCircle = container.querySelectorAll('circle')[1]

    expect(progressCircle).toHaveAttribute('stroke-dasharray', '100 100')
  })

  it('clampa valores abaixo de 0 para 0, sem quebrar o SVG', () => {
    const { container } = render(<Gauge value={-10} label="Índice de saúde" />)
    const progressCircle = container.querySelectorAll('circle')[1]

    expect(progressCircle).toHaveAttribute('stroke-dasharray', '0 100')
  })

  it('clampa valores acima de 100 para 100, sem quebrar o SVG', () => {
    const { container } = render(<Gauge value={150} label="Índice de saúde" />)
    const progressCircle = container.querySelectorAll('circle')[1]

    expect(progressCircle).toHaveAttribute('stroke-dasharray', '100 100')
  })

  it('expõe aria-label coerente com o valor exibido', () => {
    render(<Gauge value={82} label="Índice de saúde" />)

    const svg = screen.getByRole('img')
    expect(svg).toHaveAttribute('aria-label', 'Índice de saúde: 82%')
  })

  it('usa valueLabel customizado no aria-label e no centro quando informado', () => {
    render(<Gauge value={82} label="Autonomia" valueLabel="8,2h" />)

    const svg = screen.getByRole('img')
    expect(svg).toHaveAttribute('aria-label', 'Autonomia: 8,2h')
    expect(screen.getByText('8,2h')).toBeInTheDocument()
  })

  it('mostra aria-label sem rótulo quando label não é informado', () => {
    render(<Gauge value={30} />)

    const svg = screen.getByRole('img')
    expect(svg).toHaveAttribute('aria-label', '30% de 100')
  })
})
