import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { ProductionDiagnosticPanel, buildProductionDiagnosis } from './ProductionDiagnosticPanel'
import { anomalyPayload, fallbackPhotovoltaicSummaryPayload, photovoltaicSummaryPayload } from '../test/dashboardFixtures'
import type { AnomalyFetchState } from '../lib/dashboard/contracts'
import { parseAnomalyDashboard } from '../lib/dashboard/contracts'
import { parsePhotovoltaicSummary } from '../lib/dashboard/photovoltaic-contracts'

const EXPECTED_PRODUCTION = parsePhotovoltaicSummary(photovoltaicSummaryPayload).expectedProduction
const UNAVAILABLE_EXPECTED_PRODUCTION = parsePhotovoltaicSummary(fallbackPhotovoltaicSummaryPayload).expectedProduction

function anomalyState(payload: unknown = anomalyPayload): AnomalyFetchState {
  return {
    data: parseAnomalyDashboard(payload),
    loading: false,
    error: null,
  }
}

describe('ProductionDiagnosticPanel', () => {
  it('usa estado operacional enquanto o diagnóstico de produção ainda está carregando', () => {
    render(
      <ProductionDiagnosticPanel
        anomalyState={{ data: null, loading: true, error: null }}
        expectedProduction={null}
      />,
    )

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Diagnóstico de produção')
    expect(screen.getByRole('heading', { level: 2, name: 'Montando diagnóstico de produção' })).toBeInTheDocument()
    expect(status).toHaveTextContent('Aguardando histórico diário e referência esperada.')
    expect(status).toHaveTextContent('A interface evita classificar perda antes de receber os dados mínimos.')

    const signals = screen.getByRole('group', { name: 'Sinais do diagnóstico de produção' })
    expect(within(signals).getByText('Pior dia')).toBeInTheDocument()
    expect(within(signals).getByText('Desempenho do período')).toBeInTheDocument()
  })

  it('usa alerta operacional quando o histórico diário não carrega', () => {
    render(
      <ProductionDiagnosticPanel
        anomalyState={{ data: null, loading: false, error: 'SERVER_ERROR' }}
        expectedProduction={EXPECTED_PRODUCTION}
      />,
    )

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Diagnóstico indisponível')
    expect(alert).toHaveTextContent('O histórico diário não carregou com sucesso.')
    expect(alert).toHaveTextContent('Tentar atualizar o histórico de produção antes de decidir ação operacional.')
  })
  it('transforma anomalia recorrente em causa, perda estimada e próxima ação', () => {
    render(
      <ProductionDiagnosticPanel
        anomalyState={anomalyState()}
        expectedProduction={EXPECTED_PRODUCTION}
      />,
    )

    expect(screen.getByRole('heading', { level: 2, name: 'Diagnóstico: perda recorrente de produção' })).toBeInTheDocument()
    expect(screen.getByText('Confiança alta')).toBeInTheDocument()
    expect(screen.getByText(/2 dias seguidos abaixo do esperado/)).toBeInTheDocument()
    expect(screen.getByText(/pior dia em 29\/07\/2026/)).toBeInTheDocument()
    expect(screen.getByText(/Perda estimada de 10 kWh no período analisado/)).toBeInTheDocument()
    expect(screen.getByText(/cruzar com Técnico/)).toBeInTheDocument()

    expect(screen.getByText('Monitorar próximos dias')).toBeInTheDocument()
    expect(screen.getByText('Operação')).toBeInTheDocument()
    expect(screen.getByText('Evidências usadas')).toBeInTheDocument()
    expect(screen.getByText(/Pior dia: 29\/07\/2026/)).toBeInTheDocument()

    const signals = screen.getByRole('group', { name: 'Sinais do diagnóstico de produção' })
    expect(within(signals).getByText('Pior dia')).toBeInTheDocument()
    expect(within(signals).getByText('29/07/2026 · -13,6%')).toBeInTheDocument()
    expect(within(signals).getByText('Perda estimada')).toBeInTheDocument()
    expect(within(signals).getByText('6 kWh no pior dia · 10 kWh no período')).toBeInTheDocument()

    const playbook = screen.getByRole('list', { name: 'Plano operacional de produção' })
    expect(within(playbook).getByText('Acompanhar repetição')).toBeInTheDocument()
    expect(within(playbook).getByText('Separar clima de falha')).toBeInTheDocument()
    expect(within(playbook).getByText('Escalar se persistir')).toBeInTheDocument()
  })

  it('mostra o critério de alerta de 7 dias usado pelo gráfico de produção', () => {
    const state = anomalyState({
      plant_id: 'plant-1',
      days_analyzed: 7,
      current_streak_days: 7,
      worst_level: 'ANOMALY',
      expected_unavailable_reason: null,
      daily: Array.from({ length: 7 }, (_, index) => ({
        date: `2026-08-${String(index + 1).padStart(2, '0')}`,
        actual_production_kwh: 70,
        expected_production_kwh: 100,
        level: 'ANOMALY',
        deviation_percent: -30,
        irradiation_kwh_m2: null,
      })),
    })

    render(
      <ProductionDiagnosticPanel
        anomalyState={state}
        expectedProduction={EXPECTED_PRODUCTION}
      />,
    )

    expect(screen.getByText('Critério de alerta')).toBeInTheDocument()
    expect(screen.getByText('Alerta crítico')).toBeInTheDocument()
    expect(screen.getByText(/Média de 7 dias em 70% do esperado/)).toBeInTheDocument()
    expect(screen.getByText(/Regra: 7 dias contra esperado/)).toBeInTheDocument()
  })

  it('não fabrica perda quando há produção real, mas não há referência esperada', () => {
    const state = anomalyState({
      plant_id: 'plant-1',
      days_analyzed: 1,
      current_streak_days: 0,
      worst_level: null,
      expected_unavailable_reason: 'REFERENCE_YEAR_INCOMPLETE',
      daily: [
        {
          date: '2026-07-30',
          actual_production_kwh: 40,
          expected_production_kwh: null,
          level: null,
          deviation_percent: null,
          irradiation_kwh_m2: null,
        },
      ],
    })

    const diagnosis = buildProductionDiagnosis({
      anomalyState: state,
      expectedProduction: UNAVAILABLE_EXPECTED_PRODUCTION,
    })

    expect(diagnosis.tone).toBe('neutral')
    expect(diagnosis.title).toBe('Produção real disponível, sem referência esperada')
    expect(diagnosis.impact).toMatch(/não dá para estimar perda/)
  })

  it('mostra produção dentro do esperado quando não há desvio relevante', () => {
    const state = anomalyState({
      plant_id: 'plant-1',
      days_analyzed: 2,
      current_streak_days: 0,
      worst_level: 'NORMAL',
      expected_unavailable_reason: null,
      daily: [
        {
          date: '2026-07-29',
          actual_production_kwh: 45,
          expected_production_kwh: 44,
          level: 'NORMAL',
          deviation_percent: 2.3,
          irradiation_kwh_m2: null,
        },
        {
          date: '2026-07-30',
          actual_production_kwh: 44,
          expected_production_kwh: 44,
          level: 'NORMAL',
          deviation_percent: 0,
          irradiation_kwh_m2: null,
        },
      ],
    })

    render(
      <ProductionDiagnosticPanel
        anomalyState={state}
        expectedProduction={EXPECTED_PRODUCTION}
      />,
    )

    expect(screen.getByRole('heading', { level: 2, name: 'Diagnóstico: produção dentro do esperado' })).toBeInTheDocument()
    expect(screen.getByText(/Não há desvio relevante/)).toBeInTheDocument()
    expect(screen.getByText(/Manter acompanhamento/)).toBeInTheDocument()
  })
})
