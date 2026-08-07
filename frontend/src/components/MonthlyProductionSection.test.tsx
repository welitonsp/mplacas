import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { MonthlyProductionHistoryResponse } from '../lib/dashboard/monthly-history-contracts'
import { MonthlyProductionSection } from './MonthlyProductionSection'

function buildHistory(
  overrides: Partial<MonthlyProductionHistoryResponse> = {}
): MonthlyProductionHistoryResponse {
  return {
    plantId: '11111111-1111-1111-1111-111111111111',
    limit: 12,
    cyclesReturned: 3,
    cycles: [
      {
        referenceMonth: '2026-03',
        billId: 'bill-1',
        status: 'STABLE',
        productionKwh: 1000,
        quality: { missingDays: 0, provisionalDays: 0, incompleteDays: 0, unavailableDays: 0 },
      },
      {
        referenceMonth: '2026-04',
        billId: 'bill-2',
        status: 'STABLE',
        productionKwh: 1100,
        quality: { missingDays: 0, provisionalDays: 2, incompleteDays: 0, unavailableDays: 0 },
      },
      {
        referenceMonth: '2026-05',
        billId: 'bill-3',
        status: 'STABLE',
        productionKwh: 950,
        quality: { missingDays: 3, provisionalDays: 0, incompleteDays: 0, unavailableDays: 0 },
      },
    ],
    ...overrides,
  }
}

describe('MonthlyProductionSection', () => {
  it('renderiza uma barra por ciclo, em ordem cronológica, com rótulo e valor em kWh', () => {
    render(<MonthlyProductionSection history={buildHistory()} />)

    expect(screen.getByText('mar/26')).toBeInTheDocument()
    expect(screen.getByText('abr/26')).toBeInTheDocument()
    expect(screen.getByText('mai/26')).toBeInTheDocument()
    expect(screen.getByText('1.000 kWh')).toBeInTheDocument()
  })

  it('mostra o selo de dados parciais só no ciclo com missingDays/unavailableDays > 0', () => {
    render(<MonthlyProductionSection history={buildHistory()} />)

    // Só o ciclo de mai/26 (missingDays: 3) tem a lacuna que dispara o selo.
    expect(screen.getAllByText('dados parciais')).toHaveLength(1)
  })

  it('não mostra o selo quando a única lacuna é provisionalDays/incompleteDays', () => {
    const history = buildHistory({
      cycles: [
        {
          referenceMonth: '2026-05',
          billId: 'bill-1',
          status: 'STABLE',
          productionKwh: 900,
          quality: { missingDays: 0, provisionalDays: 5, incompleteDays: 2, unavailableDays: 0 },
        },
      ],
    })
    render(<MonthlyProductionSection history={history} />)

    expect(screen.queryByText('dados parciais')).not.toBeInTheDocument()
  })

  it('mostra "sem dado" para ciclo com production_kwh null sem fabricar barra zerada', () => {
    const history = buildHistory({
      cycles: [
        {
          referenceMonth: '2026-05',
          billId: 'bill-1',
          status: 'STABLE',
          productionKwh: null,
          quality: null,
        },
      ],
    })
    render(<MonthlyProductionSection history={history} />)

    expect(screen.getByText('sem dado')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('mostra mensagem neutra quando não há nenhum ciclo fechado', () => {
    render(<MonthlyProductionSection history={buildHistory({ cyclesReturned: 0, cycles: [] })} />)

    expect(
      screen.getByText('Ainda não há ciclo de faturamento fechado para esta usina.')
    ).toBeInTheDocument()
  })

  it('mostra a barra única e o aviso de comparação quando há só um ciclo', () => {
    const history = buildHistory({
      cyclesReturned: 1,
      cycles: [
        {
          referenceMonth: '2026-05',
          billId: 'bill-1',
          status: 'STABLE',
          productionKwh: 900,
          quality: null,
        },
      ],
    })
    render(<MonthlyProductionSection history={history} />)

    expect(screen.getByText('mai/26')).toBeInTheDocument()
    expect(
      screen.getByText('Comparação disponível a partir do segundo ciclo fechado.')
    ).toBeInTheDocument()
  })

  it('mostra um estado de carregamento (sem barra) quando history é null', () => {
    render(<MonthlyProductionSection history={null} />)

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(
      screen.queryByText('Ainda não há ciclo de faturamento fechado para esta usina.')
    ).not.toBeInTheDocument()
  })
})
