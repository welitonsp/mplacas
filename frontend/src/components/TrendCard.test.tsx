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
  it('renderiza as 5 métricas de tendência, incluindo o delta do índice de saúde', () => {
    render(<TrendCard trend={buildTrend()} />)

    expect(screen.getByText('Produção')).toBeInTheDocument()
    expect(screen.getByText('Consumo total')).toBeInTheDocument()
    expect(screen.getByText('Energia importada')).toBeInTheDocument()
    expect(screen.getByText('Autossuficiência')).toBeInTheDocument()
    expect(screen.getByText('Índice de saúde')).toBeInTheDocument()
    expect(screen.getByText('-5 pts')).toBeInTheDocument()
  })

  it('mostra o delta do índice de saúde positivo com sinal de mais', () => {
    render(<TrendCard trend={buildTrend({ metrics: { ...buildTrend().metrics, health_score_delta: 8 } })} />)

    expect(screen.getByText('+8 pts')).toBeInTheDocument()
  })
})
