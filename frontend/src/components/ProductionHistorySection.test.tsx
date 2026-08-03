import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProductionHistorySection } from './ProductionHistorySection'
import type { AnomalyDailyPoint, AnomalyFetchState } from '../lib/dashboard/contracts'
import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'

function buildDaily(overrides: Partial<AnomalyDailyPoint> = {}): AnomalyDailyPoint {
  return {
    date: '2026-08-01',
    actual_production_kwh: 40,
    expected_production_kwh: 44,
    level: 'NORMAL',
    deviation_percent: -9,
    irradiation_kwh_m2: null,
    ...overrides,
  }
}

const AVAILABLE: ExpectedDailyProduction = { available: true, kwh: 44 }

describe('ProductionHistorySection', () => {
  it('mostra o percentual de desempenho e a legenda "Esperado" quando a produção esperada está disponível', () => {
    const anomalyState: AnomalyFetchState = {
      loading: false,
      error: null,
      data: {
        plant_id: 'p1',
        days_analyzed: 1,
        current_streak_days: 0,
        worst_level: 'NORMAL',
        daily: [buildDaily()],
      },
    }

    render(<ProductionHistorySection anomalyState={anomalyState} expectedProduction={AVAILABLE} />)

    expect(screen.getByText(/Desempenho:/)).toBeInTheDocument()
    expect(screen.getByText('Esperado')).toBeInTheDocument()
  })

  it.each([
    ['NO_PERFORMANCE_HISTORY', null, /histórico de desempenho insuficiente/] as const,
    ['REFERENCE_YEAR_INCOMPLETE', '2027-03-14', /disponível a partir de 14\/03\/2027/] as const,
    ['INSUFFICIENT_SEASONAL_SAMPLES', null, /amostras sazonais insuficientes/] as const,
  ])(
    'mostra a mensagem específica para %s e não renderiza percentual nem linha tracejada',
    (reason, referenceCompleteOn, expectedMessage) => {
      const anomalyState: AnomalyFetchState = { loading: false, data: null, error: null }
      const expectedProduction: ExpectedDailyProduction = {
        available: false,
        reason,
        referenceCompleteOn,
      }

      render(
        <ProductionHistorySection anomalyState={anomalyState} expectedProduction={expectedProduction} />
      )

      expect(screen.getByText(expectedMessage)).toBeInTheDocument()
      expect(screen.queryByText(/Desempenho:/)).not.toBeInTheDocument()
      expect(screen.queryByText('Esperado')).not.toBeInTheDocument()
    }
  )

  it('mostra o esqueleto de carregamento enquanto a produção esperada ainda não chegou', () => {
    const anomalyState: AnomalyFetchState = { loading: true, data: null, error: null }
    const { container } = render(
      <ProductionHistorySection anomalyState={anomalyState} expectedProduction={null} />
    )
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
    expect(screen.queryByText(/Desempenho:/)).not.toBeInTheDocument()
  })

  it('mostra mensagem de "sem dado ainda" (não de erro) quando o histórico responde 404', () => {
    const anomalyState: AnomalyFetchState = { loading: false, data: null, error: 'NOT_FOUND' }

    render(<ProductionHistorySection anomalyState={anomalyState} expectedProduction={AVAILABLE} />)

    expect(
      screen.getByText('Ainda não há dado de produção diária coletado para este período.')
    ).toBeInTheDocument()
    expect(screen.queryByText('Tentar novamente')).not.toBeInTheDocument()
  })

  it('mostra mensagem de falha do sistema com opção de retry quando o histórico responde 500', () => {
    const anomalyState: AnomalyFetchState = { loading: false, data: null, error: 'SERVER_ERROR' }
    const onRetry = vi.fn()

    render(
      <ProductionHistorySection
        anomalyState={anomalyState}
        expectedProduction={AVAILABLE}
        onRetry={onRetry}
      />
    )

    expect(
      screen.getByText('Não foi possível carregar o histórico de produção diária. Tente novamente.')
    ).toBeInTheDocument()
    screen.getByText('Tentar novamente').click()
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
