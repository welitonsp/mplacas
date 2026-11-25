import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { HomeSavingsCard } from './HomeSavingsCard'
import type { ExecutiveIndicators } from '../../lib/dashboard/contracts'

const indicators = {
  estimated_savings_brl: '264.00',
  savings_unavailable_reason: null,
  bill_without_solar_brl: '334.22',
  total_amount_brl: '70.22',
} as unknown as ExecutiveIndicators

describe('HomeSavingsCard', () => {
  it('rotula o valor da fatura como "Valor da fatura" (o sistema não sabe se foi paga)', () => {
    render(
      <MemoryRouter>
        <HomeSavingsCard indicators={indicators} referenceMonth="2026-11" financialReturn={null} partial={false} />
      </MemoryRouter>,
    )

    expect(screen.getByText('Valor da fatura').nextElementSibling?.textContent).toMatch(/70,22/)
    expect(screen.queryByText(/você pagou/i)).not.toBeInTheDocument()
    expect(screen.getByText('Estimado')).toBeInTheDocument()
  })
})
