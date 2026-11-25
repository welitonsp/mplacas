import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TrendCard } from './TrendCard'
import type { ExecutiveTrend } from '../lib/dashboard/contracts'

function buildTrend(overrides: Partial<ExecutiveTrend> = {}): ExecutiveTrend {
  return {
    current_reference_month: '2026-07',
    previous_reference_month: '2026-06',
    metrics: {
      production: { absolute_delta: 10, percent_delta: 2, direction: 'UP' },
      total_consumption: { absolute_delta: 5, percent_delta: 1, direction: 'UP' },
      imported_energy: { absolute_delta: -3, percent_delta: -2, direction: 'DOWN' },
      self_sufficiency_delta_points: 1.5,
      health_score_delta: -5,
    },
    diagnostics: [],
    ...overrides,
  }
}

describe('TrendCard', () => {
  it('renderiza as métricas de tendência e NÃO mostra o índice de saúde (ADR-083)', () => {
    render(<TrendCard trend={buildTrend()} />)

    expect(screen.getByText('Produção')).toBeInTheDocument()
    expect(screen.getByText('Consumo total')).toBeInTheDocument()
    expect(screen.getByText('Energia importada')).toBeInTheDocument()
    expect(screen.getByText('Autossuficiência')).toBeInTheDocument()
    expect(screen.queryByText('Índice de saúde')).not.toBeInTheDocument()
    expect(screen.queryByText(/pts/)).not.toBeInTheDocument()
  })

  it('formata o período como mês abreviado, não como AAAA-MM cru', () => {
    render(
      <TrendCard
        trend={buildTrend({ previous_reference_month: '2026-10', current_reference_month: '2026-11' })}
      />
    )

    expect(screen.getByText('out/26 → nov/26')).toBeInTheDocument()
    expect(screen.queryByText(/2026-10/)).not.toBeInTheDocument()
  })
})
