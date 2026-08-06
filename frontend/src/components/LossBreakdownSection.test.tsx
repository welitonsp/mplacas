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
  it('renderiza as oito categorias, na ordem do backend, com valor, unidade e selo de evidência', () => {
    render(<LossBreakdownSection losses={buildLosses()} unavailableReason={null} />)

    const labels = [
      'Comunicação (dados ausentes)',
      'Indisponibilidade',
      'Clipping (limite do inversor)',
      'Sujeira (soiling)',
      'Sombreamento',
      'Temperatura',
      'Degradação',
      'Não explicada',
    ]
    for (const label of labels) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }

    // Ordem de entrada preservada — ADR-065 §4, não reordenar por severidade/valor.
    const renderedLabels = screen.getAllByTitle(/./, { exact: false }).map((node) => node.textContent)
    expect(renderedLabels).toEqual(labels)

    // Sete categorias têm valor numérico (progressbar); DEGRADATION é
    // NOT_ASSESSABLE (estimated_loss_percent: null) e não vira barra fabricada.
    expect(screen.getAllByRole('progressbar')).toHaveLength(7)
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Degradação: —')

    // Percentuais aparecem sempre com "%" visível, junto do valor.
    expect(screen.getByText('2,3%')).toBeInTheDocument()
    expect(screen.getByText('1,5%')).toBeInTheDocument()

    // Selo de evidência continua visível ao lado de cada barra.
    expect(screen.getAllByText('Não detectada').length).toBeGreaterThan(0)
    expect(screen.getByText('Possível causa')).toBeInTheDocument()
    expect(screen.getByText('Evidência de causa')).toBeInTheDocument()
    expect(screen.getByText('Não avaliável')).toBeInTheDocument()

    // Item sem valor (NOT_ASSESSABLE) preserva a mensagem de limitação.
    expect(screen.getByText('Baseline insuficiente.')).toBeInTheDocument()
  })

  it('mostra mensagem específica em vez de card vazio quando losses está indisponível', () => {
    render(<LossBreakdownSection losses={null} unavailableReason="NO_LOSS_ASSESSMENTS" />)

    expect(screen.getByText(/causas de perda ainda não disponível/)).toBeInTheDocument()
  })
})
