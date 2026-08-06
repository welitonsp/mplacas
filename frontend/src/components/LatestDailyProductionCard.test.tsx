import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { AnomalyDashboardResponse, AnomalyFetchState } from '../lib/dashboard/contracts'
import { LatestDailyProductionCard } from './LatestDailyProductionCard'

function daily(overrides: Partial<AnomalyDashboardResponse> = {}): AnomalyFetchState {
  return {
    data: {
      plant_id: 'plant-1',
      days_analyzed: 2,
      current_streak_days: 0,
      worst_level: 'NORMAL',
      daily: [
        {
          date: '2026-08-04',
          actual_production_kwh: 38,
          expected_production_kwh: 44,
          level: 'ATTENTION',
          deviation_percent: -13.6,
          irradiation_kwh_m2: null,
        },
        {
          date: '2026-08-05',
          actual_production_kwh: 40,
          expected_production_kwh: 44,
          level: 'NORMAL',
          deviation_percent: -9,
          irradiation_kwh_m2: null,
        },
      ],
      ...overrides,
    },
    loading: false,
    error: null,
  }
}

describe('LatestDailyProductionCard', () => {
  it('mostra skeleton enquanto o histórico ainda está carregando', () => {
    const { container } = render(
      <LatestDailyProductionCard anomalyState={{ data: null, loading: true, error: null }} />
    )

    expect(container.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('compara a produção real do último dia com dado contra a esperada do mesmo dia', () => {
    render(<LatestDailyProductionCard anomalyState={daily()} />)

    expect(screen.getByText('Produção de 05/08/2026 vs. esperada')).toBeInTheDocument()
    expect(screen.getByText('40 kWh')).toBeInTheDocument()
    expect(screen.getByText(/esperado 44 kWh/)).toBeInTheDocument()
    expect(screen.getByText(/-9,1%/)).toBeInTheDocument()
  })

  it('mostra só a barra real, sem desvio fabricado, quando o esperado do último dia é null', () => {
    render(
      <LatestDailyProductionCard
        anomalyState={daily({
          daily: [
            {
              date: '2026-08-05',
              actual_production_kwh: 40,
              expected_production_kwh: null,
              level: 'NORMAL',
              deviation_percent: null,
              irradiation_kwh_m2: null,
            },
          ],
        })}
      />
    )

    expect(screen.getByText('40 kWh')).toBeInTheDocument()
    expect(screen.queryByText(/esperado/)).not.toBeInTheDocument()
    expect(screen.queryByTestId('bullet-target-tick')).not.toBeInTheDocument()
  })

  it('ignora o dia mais recente sem produção real coletada ainda e usa o último dia com dado', () => {
    render(
      <LatestDailyProductionCard
        anomalyState={daily({
          daily: [
            {
              date: '2026-08-04',
              actual_production_kwh: 38,
              expected_production_kwh: 44,
              level: 'ATTENTION',
              deviation_percent: -13.6,
              irradiation_kwh_m2: null,
            },
            {
              date: '2026-08-05',
              actual_production_kwh: null,
              expected_production_kwh: 44,
              level: 'NORMAL',
              deviation_percent: null,
              irradiation_kwh_m2: null,
            },
          ],
        })}
      />
    )

    expect(screen.getByText('Produção de 04/08/2026 vs. esperada')).toBeInTheDocument()
    expect(screen.getByText('38 kWh')).toBeInTheDocument()
  })

  it('mostra estado indisponível explícito quando não há nenhum dia com produção real coletada', () => {
    render(<LatestDailyProductionCard anomalyState={{ data: null, loading: false, error: null }} />)

    expect(screen.getByText('Produção do último dia vs. esperada')).toBeInTheDocument()
    expect(
      screen.getByText('Ainda não há produção diária registrada para comparar com o esperado.')
    ).toBeInTheDocument()
  })
})
