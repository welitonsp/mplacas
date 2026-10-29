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
    expect(within(signals).getByText('Maior desvio')).toBeInTheDocument()
    expect(within(signals).getByText('Perda estimada')).toBeInTheDocument()
    // Saíram por repetir o gráfico/o aviso da mesma tela (ADR-077, decisão 15).
    expect(within(signals).queryByText('Desempenho do período')).not.toBeInTheDocument()
    expect(within(signals).queryByText('Dias abaixo')).not.toBeInTheDocument()
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
    expect(screen.getByText(/A queda se repete em dias seguidos/)).toBeInTheDocument()
    expect(screen.getByText(/Cada dia a mais nessa situação aumenta a perda estimada ao lado/)).toBeInTheDocument()
    // Cada número uma vez: data/desvio do pior dia e perdas só nos sinais.
    const panelText = document.body.textContent ?? ''
    expect(panelText.match(/29\/07\/2026/g)).toHaveLength(1)
    expect(panelText.match(/10 kWh/g)).toHaveLength(1)
    expect(panelText.match(/6 kWh/g)).toHaveLength(1)
    expect(screen.getByText(/cruzar com Técnico/)).toBeInTheDocument()

    expect(screen.getByText('Monitorar próximos dias')).toBeInTheDocument()
    expect(screen.getByText('Operação')).toBeInTheDocument()
    // O bloco "Evidências usadas" saiu em 2026-08-27 (R-1). Ele repetia em
    // prosa exatamente os sinais verificados abaixo — e este teste chegava a
    // afirmar o mesmo dado duas vezes, uma na prosa e outra no grupo de sinais.
    expect(screen.queryByText('Evidências usadas')).not.toBeInTheDocument()
    expect(screen.queryByText(/Pior dia: 29\/07\/2026/)).not.toBeInTheDocument()

    const signals = screen.getByRole('group', { name: 'Sinais do diagnóstico de produção' })
    expect(within(signals).getByText('Maior desvio')).toBeInTheDocument()
    expect(within(signals).getByText('29/07/2026 · -13,6%')).toBeInTheDocument()
    expect(within(signals).queryByText('Pior dia')).not.toBeInTheDocument()
    expect(within(signals).getByText('Perda estimada')).toBeInTheDocument()
    expect(within(signals).getByText('6 kWh no pior dia · 10 kWh no período')).toBeInTheDocument()

    const playbook = screen.getByRole('list', { name: 'Plano operacional de produção' })
    expect(within(playbook).getByText('Acompanhar repetição')).toBeInTheDocument()
    expect(within(playbook).getByText('Separar clima de falha')).toBeInTheDocument()
    expect(within(playbook).getByText('Escalar se persistir')).toBeInTheDocument()
  })

  it('não repete o critério de alerta de 7 dias, que já está em "Leitura do período"', () => {
    const state = anomalyState({
      plant_id: 'plant-1',
      days_analyzed: 7,
      current_streak_days: 7,
      worst_level: 'ANOMALY',
      expected_unavailable_reason: null,
      period_yield_kwh_per_kwh_m2: null,
      yield_atypical_threshold_percent: '20',
      period_yield_sample_days: 0,
      daily: Array.from({ length: 7 }, (_, index) => ({
        date: `2026-08-${String(index + 1).padStart(2, '0')}`,
        actual_production_kwh: 70,
        expected_production_kwh: 100,
        level: 'ANOMALY',
        deviation_percent: -30,
        irradiation_kwh_m2: null,
        yield_kwh_per_kwh_m2: null,
        yield_deviation_from_median_percent: null,
      })),
    })

    render(
      <ProductionDiagnosticPanel
        anomalyState={state}
        expectedProduction={EXPECTED_PRODUCTION}
      />,
    )

    // O gatilho de alerta (rótulo e explicação) mora em "Leitura do período",
    // na mesma aba; o diagnóstico não o repete (ADR-077, decisão 15).
    expect(screen.queryByText('Critério de alerta')).not.toBeInTheDocument()
    expect(screen.queryByText(/Regra: 7 dias contra esperado/)).not.toBeInTheDocument()
  })

  it('não fabrica perda quando há produção real, mas não há referência esperada', () => {
    const state = anomalyState({
      plant_id: 'plant-1',
      days_analyzed: 1,
      current_streak_days: 0,
      worst_level: null,
      expected_unavailable_reason: 'REFERENCE_YEAR_INCOMPLETE',
      period_yield_kwh_per_kwh_m2: null,
      yield_atypical_threshold_percent: '20',
      period_yield_sample_days: 0,
      daily: [
        {
          date: '2026-07-30',
          actual_production_kwh: 40,
          expected_production_kwh: null,
          level: null,
          deviation_percent: null,
          irradiation_kwh_m2: null,
          yield_kwh_per_kwh_m2: null,
          yield_deviation_from_median_percent: null,
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
      period_yield_kwh_per_kwh_m2: null,
      yield_atypical_threshold_percent: '20',
      period_yield_sample_days: 0,
      daily: [
        {
          date: '2026-07-29',
          actual_production_kwh: 45,
          expected_production_kwh: 44,
          level: 'NORMAL',
          deviation_percent: 2.3,
          irradiation_kwh_m2: null,
          yield_kwh_per_kwh_m2: null,
          yield_deviation_from_median_percent: null,
        },
        {
          date: '2026-07-30',
          actual_production_kwh: 44,
          expected_production_kwh: 44,
          level: 'NORMAL',
          deviation_percent: 0,
          irradiation_kwh_m2: null,
          yield_kwh_per_kwh_m2: null,
          yield_deviation_from_median_percent: null,
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
