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

    const signals = screen.getByRole('group', { name: 'Sinais do diagnóstico de produção' })
    expect(within(signals).getByText('Pior dia')).toBeInTheDocument()
    expect(within(signals).getByText('29/07/2026 · -13,6%')).toBeInTheDocument()
    expect(within(signals).getByText('Perda estimada')).toBeInTheDocument()
    expect(within(signals).getByText('6 kWh no pior dia · 10 kWh no período')).toBeInTheDocument()
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
