import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
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

describe('TechnicalPerformanceSection — camada técnica colapsável (Etapa 3.4)', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    window.localStorage.clear()
  })

  it('começa expandida por padrão (decisão de 2026-08-06)', () => {
    render(<TechnicalPerformanceSection summary={SUMMARY} />)

    const toggle = screen.getByRole('button', { name: /desempenho técnico/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    const region = document.getElementById('technical-performance-content')
    expect(region).not.toBeNull()
    expect(region).not.toHaveAttribute('hidden')
    expect(screen.getByText('Performance ratio (PR)')).toBeInTheDocument()
  })

  it('colapsa ao clicar no controle e atualiza aria-expanded', () => {
    render(<TechnicalPerformanceSection summary={SUMMARY} />)

    const toggle = screen.getByRole('button', { name: /desempenho técnico/i })
    fireEvent.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    const region = document.getElementById('technical-performance-content')
    expect(region).toHaveAttribute('hidden')
    // Conteúdo continua montado no DOM (não desmontado condicionalmente),
    // só inacessível por leitor de tela via `hidden`.
    expect(screen.getByText('Performance ratio (PR)')).toBeInTheDocument()
  })

  it('aria-controls do botão aponta para o id do conteúdo, e a região tem role apropriado', () => {
    render(<TechnicalPerformanceSection summary={SUMMARY} />)

    const toggle = screen.getByRole('button', { name: /desempenho técnico/i })
    const contentId = toggle.getAttribute('aria-controls')
    expect(contentId).toBe('technical-performance-content')

    const region = document.getElementById(contentId as string)
    expect(region).toHaveAttribute('role', 'region')
  })

  it('persiste a preferência de expansão em localStorage entre montagens', () => {
    const { unmount } = render(<TechnicalPerformanceSection summary={SUMMARY} />)

    fireEvent.click(screen.getByRole('button', { name: /desempenho técnico/i }))
    expect(window.localStorage.getItem('mplacas:technical-performance-expanded')).toBe('false')
    unmount()

    render(<TechnicalPerformanceSection summary={SUMMARY} />)
    expect(screen.getByRole('button', { name: /desempenho técnico/i })).toHaveAttribute(
      'aria-expanded',
      'false'
    )
  })
})
