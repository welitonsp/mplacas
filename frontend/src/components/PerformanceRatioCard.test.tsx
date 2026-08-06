import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PerformanceRatioCard } from './PerformanceRatioCard'

describe('PerformanceRatioCard', () => {
  it('renderiza PR bruto e corrigido por temperatura com % visível', () => {
    render(
      <PerformanceRatioCard
        performance={{
          dc_capacity_kwp: '10.000',
          performance_ratio: '0.8200',
          temperature_corrected_performance_ratio: '0.8500',
          final_yield_kwh_per_kwp: '4.400',
          reporting_availability_ratio: '0.9800',
        }}
        unavailableReason={null}
      />
    )

    expect(screen.getByText('82%')).toBeInTheDocument()
    expect(screen.getByText('85%')).toBeInTheDocument()
    expect(screen.getByText('Bruto')).toBeInTheDocument()
    expect(screen.getByText('Corrigido por temperatura')).toBeInTheDocument()

    const gauges = screen.getAllByRole('img')
    expect(gauges).toHaveLength(2)
    expect(gauges[0]).toHaveAttribute('aria-label', 'Bruto: 82%')
    expect(gauges[1]).toHaveAttribute('aria-label', 'Corrigido por temperatura: 85%')
  })

  it('mostra placeholder neutro (sem gráfico fabricado) quando o PR corrigido é nulo', () => {
    render(
      <PerformanceRatioCard
        performance={{
          dc_capacity_kwp: '10.000',
          performance_ratio: '0.8200',
          temperature_corrected_performance_ratio: null,
          final_yield_kwh_per_kwp: '4.400',
          reporting_availability_ratio: '0.9800',
        }}
        unavailableReason={null}
      />
    )

    expect(screen.getAllByRole('img')).toHaveLength(1)
    expect(screen.getByText('82%')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('mostra mensagem específica em vez de card vazio quando performance está indisponível', () => {
    render(<PerformanceRatioCard performance={null} unavailableReason="NO_PERFORMANCE_RESULTS" />)

    expect(screen.getByText(/Desempenho técnico ainda não disponível/)).toBeInTheDocument()
    expect(screen.queryByText('%')).not.toBeInTheDocument()
  })
})
