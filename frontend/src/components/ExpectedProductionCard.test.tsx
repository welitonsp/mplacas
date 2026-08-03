import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ExpectedProductionCard } from './ExpectedProductionCard'

describe('ExpectedProductionCard', () => {
  it('mostra skeleton enquanto o baseline sazonal ainda está carregando (expectedProduction === null)', () => {
    const { container } = render(<ExpectedProductionCard expectedProduction={null} />)

    expect(container.querySelector('.animate-pulse')).not.toBeNull()
    expect(screen.queryByText(/Produção esperada/)).not.toBeInTheDocument()
  })

  it('mostra o valor médio diário esperado quando disponível', () => {
    render(<ExpectedProductionCard expectedProduction={{ available: true, kwh: 44.5 }} />)

    expect(screen.getByText('Produção esperada (média diária)')).toBeInTheDocument()
    expect(screen.getByText('kWh/dia')).toBeInTheDocument()
    expect(screen.getByText(/44,5/)).toBeInTheDocument()
  })

  it('mostra o motivo específico quando o baseline sazonal não está disponível', () => {
    render(
      <ExpectedProductionCard
        expectedProduction={{
          available: false,
          reason: 'NO_PERFORMANCE_HISTORY',
          referenceCompleteOn: null,
        }}
      />
    )

    expect(screen.getByText('Produção esperada')).toBeInTheDocument()
    expect(
      screen.getByText(/histórico de desempenho insuficiente para esta usina/)
    ).toBeInTheDocument()
  })
})
