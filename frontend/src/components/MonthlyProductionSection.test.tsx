import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
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
  it('renderiza uma coluna por ciclo, em ordem cronológica (leitura esquerda→direita), com rótulo e valor em kWh', () => {
    render(<MonthlyProductionSection history={buildHistory()} />)

    // Escopado à parte visual do gráfico (`data-testid="column-series-visual"`,
    // ver `ColumnSeries.tsx`) — os mesmos rótulos/valores aparecem de novo,
    // de propósito, na tabela `sr-only` mais abaixo, o que tornaria
    // `screen.getByText` ambíguo sem esse escopo.
    const visual = within(screen.getByTestId('column-series-visual'))
    expect(visual.getByText('mar/26')).toBeInTheDocument()
    expect(visual.getByText('abr/26')).toBeInTheDocument()
    expect(visual.getByText('mai/26')).toBeInTheDocument()
    expect(visual.getByText('1.000 kWh')).toBeInTheDocument()

    // Ordem cronológica preservada no DOM (nunca reordenado) — mesma garantia
    // que a lista horizontal antiga já dava, agora verificada pela ordem dos
    // rótulos do eixo X.
    const labels = visual.getAllByTitle(/^(mar|abr|mai)\/26$/).map((el) => el.textContent)
    expect(labels).toEqual(['mar/26', 'abr/26', 'mai/26'])
  })

  it('expõe um único gráfico (role="img") com o equivalente textual completo da série, unidade incluída', () => {
    render(<MonthlyProductionSection history={buildHistory()} />)

    const ariaLabel = screen.getByRole('img').getAttribute('aria-label') ?? ''
    expect(ariaLabel).toContain('mar/26: 1.000 kWh')
    expect(ariaLabel).toContain('abr/26: 1.100 kWh')
    expect(ariaLabel).toContain('mai/26: 950 kWh')
  })

  it('mostra o selo de dados parciais só no ciclo com missingDays/unavailableDays > 0', () => {
    render(<MonthlyProductionSection history={buildHistory()} />)

    // Só o ciclo de mai/26 (missingDays: 3) tem a lacuna que dispara o selo.
    expect(screen.getAllByText('dados parciais')).toHaveLength(1)
  })

  it('ciclo parcial é distinguível via atributo (data-quality), não só visualmente', () => {
    render(<MonthlyProductionSection history={buildHistory()} />)

    const columns = document.querySelectorAll('[data-quality]')
    expect(columns).toHaveLength(3)
    const qualities = Array.from(columns).map((el) => el.getAttribute('data-quality'))
    // mar/26 e abr/26 completos, mai/26 parcial — mesma ordem cronológica.
    expect(qualities).toEqual(['complete', 'complete', 'partial'])
  })

  it('o aria-label do gráfico marca o ciclo parcial explicitamente (não só a cor da coluna)', () => {
    render(<MonthlyProductionSection history={buildHistory()} />)

    const chart = screen.getByRole('img')
    expect(chart.getAttribute('aria-label')).toContain('mai/26: 950 kWh, dados parciais')
  })

  it('mostra a contagem exata de dias sem dado do ciclo parcial, nunca só em tooltip', () => {
    render(<MonthlyProductionSection history={buildHistory()} />)

    // Texto visível abaixo da coluna (não aria-hidden em ancestral direto
    // marcado, mas parte do DOM real e consultável por `getByText`).
    expect(screen.getByText('3 dias sem dado')).toBeInTheDocument()
  })

  it('exibe uma entrada de legenda explicando o selo "dados parciais" quando há ao menos um ciclo com lacuna', () => {
    render(<MonthlyProductionSection history={buildHistory()} />)

    expect(
      screen.getByText('Dados parciais — dias sem telemetria coletada')
    ).toBeInTheDocument()
  })

  it('não exibe a legenda de "dados parciais" quando nenhum ciclo tem lacuna', () => {
    const history = buildHistory({
      cycles: [
        {
          referenceMonth: '2026-05',
          billId: 'bill-1',
          status: 'STABLE',
          productionKwh: 900,
          quality: { missingDays: 0, provisionalDays: 0, incompleteDays: 0, unavailableDays: 0 },
        },
      ],
    })
    render(<MonthlyProductionSection history={history} />)

    expect(
      screen.queryByText('Dados parciais — dias sem telemetria coletada')
    ).not.toBeInTheDocument()
  })

  it('expõe uma tabela sr-only com ciclo, valor e qualidade dos dados por linha', () => {
    render(<MonthlyProductionSection history={buildHistory()} />)

    const table = document.querySelector('table.sr-only') as HTMLElement
    expect(table).toBeInTheDocument()

    const partialRow = within(table).getByText('mai/26').closest('tr') as HTMLElement
    expect(within(partialRow).getByText('950 kWh')).toBeInTheDocument()
    expect(within(partialRow).getByText('dados parciais — 3 dias sem dado')).toBeInTheDocument()

    const completeRow = within(table).getByText('mar/26').closest('tr') as HTMLElement
    expect(within(completeRow).getByText('completo')).toBeInTheDocument()
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

  it('mostra "sem dado" para ciclo com production_kwh null sem fabricar coluna zerada', () => {
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

    expect(screen.getAllByText('sem dado').length).toBeGreaterThan(0)
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'mai/26: sem dado')
  })

  it('mostra mensagem neutra quando não há nenhum ciclo fechado', () => {
    render(<MonthlyProductionSection history={buildHistory({ cyclesReturned: 0, cycles: [] })} />)

    expect(screen.getByRole('heading', { level: 2, name: 'Sem ciclos fechados' })).toBeInTheDocument()
    expect(screen.getByText(/Ainda não há ciclo de faturamento fechado para esta usina/)).toBeInTheDocument()
  })

  it('mostra a coluna única e o aviso de comparação quando há só um ciclo', () => {
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

    expect(
      within(screen.getByTestId('column-series-visual')).getByText('mai/26')
    ).toBeInTheDocument()
    expect(
      screen.getByText('Comparação disponível a partir do segundo ciclo fechado.')
    ).toBeInTheDocument()
  })

  it('mostra um estado de carregamento (sem gráfico) quando history é null', () => {
    render(<MonthlyProductionSection history={null} />)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(
      screen.queryByText('Ainda não há ciclo de faturamento fechado para esta usina.')
    ).not.toBeInTheDocument()
  })
})
