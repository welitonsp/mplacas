import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { DiagnosticsCard } from './DiagnosticsCard'
import { combineDiagnostics, type Diagnostic, type ExecutiveDashboardResponse } from '../lib/dashboard/contracts'

function buildDashboard(diagnostics: {
  currentCycle?: Diagnostic[]
  trend?: Diagnostic[]
}): ExecutiveDashboardResponse {
  return {
    plant_id: 'plant-1',
    status: 'CRITICAL',
    headline: 'headline',
    priority_actions: [],
    current_cycle: {
      reference_month: '2026-07',
      quality: { missing_days: 0, provisional_days: 0, incomplete_days: 0, unavailable_days: 0 },
      indicators: {
        cycle_production_kwh: 500,
        imported_kwh: 120,
        injected_kwh: 80,
        estimated_self_consumption_kwh: 420,
        estimated_total_consumption_kwh: 540,
        self_consumption_rate_percent: 84,
        self_sufficiency_rate_percent: 77.7,
        grid_dependency_rate_percent: 22.3,
        exported_generation_rate_percent: 16,
        credit_coverage_rate_percent: 100,
        bill_energy_component_brl: 350.5,
        health_score: 70,
      },
      diagnostics: diagnostics.currentCycle ?? [],
    },
    trend: diagnostics.trend
      ? {
          current_reference_month: '2026-07',
          previous_reference_month: '2026-06',
          metrics: {
            production: { absolute_delta: 10, percent_delta: 2, direction: 'UP' },
            total_consumption: { absolute_delta: 5, percent_delta: 1, direction: 'UP' },
            imported_energy: { absolute_delta: -3, percent_delta: -2, direction: 'DOWN' },
            self_sufficiency_delta_points: 1.5,
            health_score_delta: -5,
          },
          diagnostics: diagnostics.trend,
        }
      : null,
  }
}

describe('DiagnosticsCard', () => {
  it('mostra o diagnóstico crítico antes do warning, com rótulo de severidade e ação recomendada', () => {
    const dashboard = buildDashboard({
      currentCycle: [
        {
          code: 'IMPORTED_ENERGY_HIGH',
          severity: 'WARNING',
          message: 'Energia importada acima do esperado',
          recommended_action: 'Revisar consumo importado',
        },
      ],
      trend: [
        {
          code: 'HEALTH_SCORE_DROPPED',
          severity: 'CRITICAL',
          message: 'Índice de saúde caiu em relação ao ciclo anterior',
          recommended_action: 'Investigar queda de desempenho',
        },
      ],
    })

    render(<DiagnosticsCard diagnostics={combineDiagnostics(dashboard)} />)

    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)

    // Crítico primeiro.
    expect(within(items[0]).getByText('Índice de saúde caiu em relação ao ciclo anterior')).toBeInTheDocument()
    expect(within(items[0]).getByText('Crítico')).toBeInTheDocument()
    expect(within(items[0]).getByText(/Investigar queda de desempenho/)).toBeInTheDocument()

    // Warning depois.
    expect(within(items[1]).getByText('Energia importada acima do esperado')).toBeInTheDocument()
    expect(within(items[1]).getByText('Atenção')).toBeInTheDocument()
    expect(within(items[1]).getByText(/Revisar consumo importado/)).toBeInTheDocument()
  })

  it('mostra estado vazio explícito quando não há diagnósticos', () => {
    render(<DiagnosticsCard diagnostics={[]} />)

    expect(screen.getByText('Nenhum diagnóstico neste ciclo.')).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })
})
