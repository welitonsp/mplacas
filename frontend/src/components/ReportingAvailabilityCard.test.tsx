import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ReportingAvailabilityCard } from './ReportingAvailabilityCard'

describe('ReportingAvailabilityCard', () => {
  it('renderiza o gauge de disponibilidade de reporte com valor e tom corretos', () => {
    render(
      <ReportingAvailabilityCard
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

    const gauge = screen.getByRole('img')
    expect(gauge).toHaveAttribute('aria-label', 'Disponibilidade de reporte: 98%')
    expect(screen.getByText('98%')).toBeInTheDocument()
  })

  it('mostra mensagem específica em vez de card vazio quando performance está indisponível', () => {
    render(<ReportingAvailabilityCard performance={null} unavailableReason="NO_PERFORMANCE_RESULTS" />)

    expect(screen.getByText(/Desempenho técnico ainda não disponível/)).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('não fabrica gauge de 0 quando reporting_availability_ratio é nulo', () => {
    render(
      <ReportingAvailabilityCard
        performance={{
          dc_capacity_kwp: '10.000',
          performance_ratio: '0.8200',
          temperature_corrected_performance_ratio: '0.8500',
          final_yield_kwh_per_kwp: '4.400',
          reporting_availability_ratio: null,
        }}
        unavailableReason={null}
      />
    )

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
