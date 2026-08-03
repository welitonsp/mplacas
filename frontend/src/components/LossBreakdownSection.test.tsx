import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { PhotovoltaicLossItem } from '../lib/dashboard/photovoltaic-contracts'
import { LossBreakdownSection } from './LossBreakdownSection'

function buildLosses(): PhotovoltaicLossItem[] {
  return [
    { category: 'COMMUNICATION', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'UNAVAILABILITY', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'CLIPPING', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'SOILING', evidence_level: 'POSSIBLE', estimated_loss_percent: '1.50', evidence_codes: ['SOILING_TREND'], limitation: null },
    { category: 'SHADING', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'TEMPERATURE', evidence_level: 'LIKELY', estimated_loss_percent: '2.30', evidence_codes: ['HIGH_CELL_TEMP'], limitation: null },
    { category: 'DEGRADATION', evidence_level: 'NOT_ASSESSABLE', estimated_loss_percent: null, evidence_codes: [], limitation: 'Baseline insuficiente.' },
    { category: 'UNEXPLAINED', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
  ]
}

describe('LossBreakdownSection', () => {
  it('renderiza as oito categorias com valor e unidade', () => {
    render(<LossBreakdownSection losses={buildLosses()} unavailableReason={null} />)

    expect(screen.getByText('Comunicação (dados ausentes)')).toBeInTheDocument()
    expect(screen.getByText('Indisponibilidade')).toBeInTheDocument()
    expect(screen.getByText('Clipping (limite do inversor)')).toBeInTheDocument()
    expect(screen.getByText('Sujeira (soiling)')).toBeInTheDocument()
    expect(screen.getByText('Sombreamento')).toBeInTheDocument()
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    expect(screen.getByText('Degradação')).toBeInTheDocument()
    expect(screen.getByText('Não explicada')).toBeInTheDocument()

    // Percentuais aparecem sempre com "%" visível.
    expect(screen.getAllByText('%').length).toBeGreaterThanOrEqual(8)
    // Item sem valor (NOT_ASSESSABLE) mostra travessão, não um número inventado.
    expect(screen.getByText('Baseline insuficiente.')).toBeInTheDocument()
  })

  it('mostra mensagem específica em vez de card vazio quando losses está indisponível', () => {
    render(<LossBreakdownSection losses={null} unavailableReason="NO_LOSS_ASSESSMENTS" />)

    expect(screen.getByText(/causas de perda ainda não disponível/)).toBeInTheDocument()
  })
})
