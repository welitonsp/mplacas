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

  it('mostra o traço quando o valor é nulo, mas mantém a unidade visível', () => {
    render(<MetricCard label="Energia importada" value={null} unit="kWh" />)

    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText('kWh')).toBeInTheDocument()
  })

  it('exibe o selo de "Parcial" quando partial=true', () => {
    render(<MetricCard label="Consumo total estimado" value={10} partial />)

    expect(screen.getByText('Parcial')).toBeInTheDocument()
  })

  it('expõe a barra de progresso com semântica ARIA quando barPercent é informado', () => {
    render(<MetricCard label="Autossuficiência" value={70} unit="%" barPercent={70} />)

    const progressbar = screen.getByRole('progressbar')
    expect(progressbar).toHaveAttribute('aria-valuenow', '70')
    expect(progressbar).toHaveAttribute('aria-valuemin', '0')
    expect(progressbar).toHaveAttribute('aria-valuemax', '100')
  })

  it('não renderiza barra de progresso quando barPercent não é informado', () => {
    render(<MetricCard label="Produção" value={10} />)

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('o valor numérico principal usa tabular-nums (Etapa 1.5)', () => {
    render(<MetricCard label="Produção no ciclo" value={123.456} unit="kWh" />)

    const valueNode = screen.getByText(/123,46/)
    expect(valueNode.className).toMatch(/\btabular-nums\b/)
  })
})
