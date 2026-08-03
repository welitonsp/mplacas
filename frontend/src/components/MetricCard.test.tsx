import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MetricCard } from './MetricCard'

describe('MetricCard', () => {
  it('renderiza label, valor formatado e unidade', () => {
    render(<MetricCard label="Produção no ciclo" value={123.456} unit="kWh" />)

    expect(screen.getByText('Produção no ciclo')).toBeInTheDocument()
    expect(screen.getByText('kWh')).toBeInTheDocument()
    expect(screen.getByText(/123,46/)).toBeInTheDocument()
  })

  it('mostra o traço quando o valor é nulo', () => {
    render(<MetricCard label="Energia importada" value={null} unit="kWh" />)

    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('exibe o selo de "Parcial" quando partial=true', () => {
    render(<MetricCard label="Consumo total estimado" value={10} partial />)

    expect(screen.getByText('Parcial')).toBeInTheDocument()
  })
})
