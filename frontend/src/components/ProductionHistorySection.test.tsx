import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
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
    yield_kwh_per_kwh_m2: null,
    yield_deviation_from_median_percent: null,
    temperature_mean_c: null,
    diagnostics: [],
    ...overrides,
  }
}

function buildAnomalyData(overrides: {
  daily?: AnomalyDailyPoint[]
  expectedUnavailableReason?: string | null
  worstLevel?: AnomalyDailyPoint['level']
} = {}) {
  return {
    plant_id: 'p1',
    days_analyzed: 1,
    current_streak_days: 0,
    period: null,
    worst_level: overrides.worstLevel ?? 'NORMAL',
    expected_unavailable_reason: overrides.expectedUnavailableReason ?? null,
    period_yield_kwh_per_kwh_m2: null,
    yield_atypical_threshold_percent: '20',
    period_yield_sample_days: 0,
    daily: overrides.daily ?? [buildDaily()],
  }
}

const AVAILABLE: ExpectedDailyProduction = {
  available: true,
  kwh: 44,
  modelVersion: 'MPLACAS_EXPECTED_DAILY_PRODUCTION_V1',
  nature: 'SEASONAL_CLEAR_SKY_P90_ENVELOPE',
}

const PERIOD_STORAGE_KEY = 'mplacas:production-history-period'

describe('ProductionHistorySection', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('mostra o percentual de desempenho e a legenda "Média diária esperada (baseline sazonal)" quando a produção esperada está disponível', () => {
    const anomalyState: AnomalyFetchState = {
      loading: false,
      error: null,
      data: buildAnomalyData(),
    }

    render(<ProductionHistorySection anomalyState={anomalyState} expectedProduction={AVAILABLE} />)

    expect(screen.getByText(/Desempenho:/)).toBeInTheDocument()
    expect(screen.getByText('Média diária esperada (baseline sazonal)')).toBeInTheDocument()
  })

  it('filtra o gráfico por 7 dias por padrão e permite alternar para 30 e 90 dias', () => {
    const daily = Array.from({ length: 10 }, (_, index) =>
      buildDaily({
        date: `2026-08-${String(index + 1).padStart(2, '0')}`,
        actual_production_kwh: (index + 1) * 10,
        expected_production_kwh: 100,
        deviation_percent: -10,
      })
    )
    const anomalyState: AnomalyFetchState = {
      loading: false,
      error: null,
      data: buildAnomalyData({ daily }),
    }

    render(<ProductionHistorySection anomalyState={anomalyState} expectedProduction={AVAILABLE} />)

    expect(screen.getByRole('button', { name: '7 dias' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Últimos 7 dias em foco')).toBeInTheDocument()
    expect(screen.getByText('Histórico de produção diária (7 dias)')).toBeInTheDocument()
    expect(screen.getAllByText('70 kWh/dia').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Tendência do recorte')).toBeInTheDocument()
    expect(screen.getByText('Em recuperação')).toBeInTheDocument()
    expect(screen.getByText('250% acima da janela anterior.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '30 dias' }))

    expect(screen.getByRole('button', { name: '30 dias' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Últimos 10 dias em foco')).toBeInTheDocument()
    expect(screen.getByText('Histórico de produção diária (10 dias)')).toBeInTheDocument()
    expect(screen.getAllByText('55 kWh/dia').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Sem comparação')).toBeInTheDocument()
    expect(screen.getByText('Precisa de janela anterior de 30 dias para comparar tendência.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '90 dias' }))

    expect(screen.getByRole('button', { name: '90 dias' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Últimos 10 dias em foco')).toBeInTheDocument()
  })

  it('lembra o período escolhido pelo usuário em localStorage', () => {
    const daily = Array.from({ length: 30 }, (_, index) =>
      buildDaily({
        date: `2026-08-${String(index + 1).padStart(2, '0')}`,
        actual_production_kwh: 55,
        expected_production_kwh: 60,
        deviation_percent: -8,
      })
    )
    const anomalyState: AnomalyFetchState = {
      loading: false,
      error: null,
      data: buildAnomalyData({ daily }),
    }

    const { unmount } = render(
      <ProductionHistorySection anomalyState={anomalyState} expectedProduction={AVAILABLE} />
    )

    fireEvent.click(screen.getByRole('button', { name: '30 dias' }))

    expect(window.localStorage.getItem(PERIOD_STORAGE_KEY)).toBe('30')

    unmount()

    render(<ProductionHistorySection anomalyState={anomalyState} expectedProduction={AVAILABLE} />)

    expect(screen.getByRole('button', { name: '30 dias' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Últimos 30 dias em foco')).toBeInTheDocument()
    expect(screen.getByText('Histórico de produção diária (30 dias)')).toBeInTheDocument()
  })

  it('mostra alerta crítico quando a média dos últimos 7 dias fica abaixo do gatilho esperado', () => {
    const daily = Array.from({ length: 7 }, (_, index) =>
      buildDaily({
        date: `2026-08-${String(index + 1).padStart(2, '0')}`,
        actual_production_kwh: 70,
        expected_production_kwh: 100,
        deviation_percent: -30,
        level: 'ANOMALY',
      })
    )
    const anomalyState: AnomalyFetchState = {
      loading: false,
      error: null,
      data: buildAnomalyData({ daily, worstLevel: 'ANOMALY' }),
    }

    render(<ProductionHistorySection anomalyState={anomalyState} expectedProduction={AVAILABLE} />)

    expect(screen.getByText('Alerta crítico')).toBeInTheDocument()
    expect(screen.getByText('Média de 7 dias em 70% do esperado.')).toBeInTheDocument()
  })

  it.each([
    ['NO_PERFORMANCE_HISTORY', null, /histórico de desempenho insuficiente/] as const,
    ['REFERENCE_YEAR_INCOMPLETE', '2027-03-14', /disponível a partir de 14\/03\/2027/] as const,
    ['INSUFFICIENT_SEASONAL_SAMPLES', null, /amostras sazonais insuficientes/] as const,
  ])(
    'mostra a mensagem específica para %s e não renderiza percentual nem linha tracejada (payload de anomalias chegou, sem expectativa e sem produção real nenhuma)',
    (reason, referenceCompleteOn, expectedMessage) => {
      // Contrato novo: `/energy/anomalies/latest` responde 200 sempre — o
      // caso "sem expectativa" chega como payload com `expected_unavailable_reason`
      // preenchido, não mais como `data: null`/`error: null` (esse combo não
      // é mais produzido por `DashboardPage`, que agora busca anomalias
      // independente do baseline sazonal).
      const anomalyState: AnomalyFetchState = {
        loading: false,
        error: null,
        data: buildAnomalyData({
          expectedUnavailableReason: reason,
          worstLevel: null,
          daily: [buildDaily({ actual_production_kwh: null, expected_production_kwh: null, level: null, deviation_percent: null })],
        }),
      }
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
      expect(screen.queryByText('Média diária esperada (baseline sazonal)')).not.toBeInTheDocument()
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

  it('monta o gráfico mesmo com produção esperada indisponível, contanto que haja produção real registrada', () => {
    // `expected_unavailable_reason` presente no PRÓPRIO payload de anomalias
    // (não mais dependente de `expectedProduction` concordar em separado) —
    // ver contrato novo de `GET /energy/anomalies/latest`.
    const anomalyState: AnomalyFetchState = {
      loading: false,
      error: null,
      data: buildAnomalyData({
        expectedUnavailableReason: 'NO_PERFORMANCE_HISTORY',
        worstLevel: null,
        daily: [buildDaily({ actual_production_kwh: 40, expected_production_kwh: null, level: null, deviation_percent: null })],
      }),
    }
    const expectedProduction: ExpectedDailyProduction = {
      available: false,
      reason: 'NO_PERFORMANCE_HISTORY',
      referenceCompleteOn: null,
    }

    render(<ProductionHistorySection anomalyState={anomalyState} expectedProduction={expectedProduction} />)

    // Não cai no fallback de texto "dados insuficientes" — o gráfico monta.
    expect(screen.getByRole('slider')).toBeInTheDocument()
    expect(screen.queryByText(/histórico de desempenho insuficiente/)).not.toBeInTheDocument()
    // Sem a linha/legenda de referência esperada, já que a produção esperada não está disponível.
    expect(screen.queryByText('Média diária esperada (baseline sazonal)')).not.toBeInTheDocument()
  })

  it('mostra o fallback de "dados insuficientes" quando não há produção real nenhuma e a esperada está indisponível', () => {
    const anomalyState: AnomalyFetchState = {
      loading: false,
      error: null,
      data: buildAnomalyData({
        expectedUnavailableReason: 'NO_PERFORMANCE_HISTORY',
        worstLevel: null,
        daily: [buildDaily({ actual_production_kwh: null, expected_production_kwh: null, level: null, deviation_percent: null })],
      }),
    }
    const expectedProduction: ExpectedDailyProduction = {
      available: false,
      reason: 'NO_PERFORMANCE_HISTORY',
      referenceCompleteOn: null,
    }

    render(<ProductionHistorySection anomalyState={anomalyState} expectedProduction={expectedProduction} />)

    expect(screen.getByText(/histórico de desempenho insuficiente/)).toBeInTheDocument()
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
  })

  it('deriva expectedAvailable do payload de anomalias, não de expectedProduction, mesmo quando as duas fontes divergem', () => {
    // `expectedProduction` (de `/photovoltaic/summary`) diz que está
    // disponível, mas o payload de anomalias (fonte real usada pelo gráfico)
    // diz que não está — a seção precisa seguir o payload de anomalias, não
    // fabricar a linha de referência esperada com base numa segunda chamada
    // de API que pode divergir dela.
    const anomalyState: AnomalyFetchState = {
      loading: false,
      error: null,
      data: buildAnomalyData({
        expectedUnavailableReason: 'REFERENCE_YEAR_INCOMPLETE',
        worstLevel: null,
        daily: [buildDaily({ actual_production_kwh: 40, expected_production_kwh: null, level: null, deviation_percent: null })],
      }),
    }

    render(<ProductionHistorySection anomalyState={anomalyState} expectedProduction={AVAILABLE} />)

    expect(screen.getByRole('slider')).toBeInTheDocument()
    expect(screen.queryByText('Média diária esperada (baseline sazonal)')).not.toBeInTheDocument()
    expect(screen.queryByText(/Desempenho:/)).not.toBeInTheDocument()
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
    const retryButton = screen.getByText('Tentar novamente')
    expect(retryButton.className).toMatch(/focus-visible:ring/)
    retryButton.click()
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
