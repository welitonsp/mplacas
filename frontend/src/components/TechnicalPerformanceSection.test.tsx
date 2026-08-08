import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { PhotovoltaicSummaryResponse } from '../lib/dashboard/photovoltaic-contracts'
import { TechnicalPerformanceSection } from './TechnicalPerformanceSection'

const SUMMARY: PhotovoltaicSummaryResponse = {
  plant_id: 'plant-1',
  performance: null,
  performance_unavailable_reason: 'NO_PERFORMANCE_RESULTS',
  baseline: null,
  baseline_unavailable_reason: 'NO_PERFORMANCE_HISTORY',
  reference_complete_on: null,
  losses: null,
  losses_unavailable_reason: 'NO_LOSS_ASSESSMENTS',
  expectedProduction: { available: false, reason: 'NO_PERFORMANCE_HISTORY', referenceCompleteOn: null },
}

describe('TechnicalPerformanceSection — sempre expandida, sem toggle (ADR-072, Etapa 2)', () => {
  it('renderiza o conteúdo diretamente, sem nenhum controle de expandir/colapsar', () => {
    render(<TechnicalPerformanceSection summary={SUMMARY} />)

    expect(screen.queryByRole('button', { name: /desempenho técnico/i })).not.toBeInTheDocument()

    const region = screen.getByRole('region', { name: 'Desempenho técnico' })
    expect(region).not.toHaveAttribute('hidden')
    expect(screen.getByText('Performance ratio (PR)')).toBeInTheDocument()
  })

  it('o título "Desempenho técnico" é um heading de nível 2', () => {
    render(<TechnicalPerformanceSection summary={SUMMARY} />)

    expect(screen.getByRole('heading', { level: 2, name: 'Desempenho técnico' })).toBeInTheDocument()
  })

  it('mostra o esqueleto de carregamento enquanto summary ainda não chegou (summary === null)', () => {
    render(<TechnicalPerformanceSection summary={null} />)

    expect(screen.queryByText('Performance ratio (PR)')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Desempenho técnico' })).toBeInTheDocument()
  })

  it('não lê nem persiste mais nenhuma preferência em localStorage (chave antiga vira estado morto)', () => {
    window.localStorage.setItem('mplacas:technical-performance-expanded', 'false')

    render(<TechnicalPerformanceSection summary={SUMMARY} />)

    // O conteúdo aparece mesmo com o valor antigo 'false' ainda gravado —
    // prova de que a chave não é mais lida.
    expect(screen.getByText('Performance ratio (PR)')).toBeInTheDocument()

    window.localStorage.removeItem('mplacas:technical-performance-expanded')
  })
})
