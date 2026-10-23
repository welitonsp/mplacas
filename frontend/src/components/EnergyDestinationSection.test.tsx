import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EnergyDestinationSection } from './EnergyDestinationSection'
import { executivePayload } from '../test/dashboardFixtures'
import type { ExecutiveIndicators } from '../lib/dashboard/contracts'

const clean = { missing_days: 0, provisional_days: 0, incomplete_days: 0, unavailable_days: 0 }

function indicators(overrides: Partial<ExecutiveIndicators> = {}): ExecutiveIndicators {
  return {
    ...(executivePayload.current_cycle.indicators as unknown as ExecutiveIndicators),
    estimated_total_consumption_kwh: '569.21',
    imported_kwh: '221',
    self_sufficiency_rate_percent: '61.2',
    ...overrides,
  }
}

describe('EnergyDestinationSection (aba Energia, ADR-083)', () => {
  it('título com o ciclo e frase que só repete os números do motor', () => {
    render(<EnergyDestinationSection indicators={indicators()} quality={clean} referenceMonth="2026-09" />)

    expect(screen.getByRole('heading', { level: 2, name: 'Para onde foi a energia — ciclo set/26' })).toBeInTheDocument()
    expect(
      screen.getByText((_, element) =>
        element?.tagName === 'P' &&
        element.textContent === 'O sol supriu 61% do consumo da casa (569 kWh, estimado); os outros 221 kWh vieram da rede.',
      ),
    ).toBeInTheDocument()
  })

  it('sem autossuficiência calculada, não inventa a frase', () => {
    render(
      <EnergyDestinationSection
        indicators={indicators({ self_sufficiency_rate_percent: null })}
        quality={clean}
        referenceMonth="2026-09"
      />,
    )

    expect(screen.queryByText(/O sol supriu/)).not.toBeInTheDocument()
  })
})
