import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { ColumnSeries } from './ColumnSeries'

describe('ColumnSeries', () => {
  it('renderiza uma coluna por item, em ordem (nunca reordenado), com rótulo e valor', () => {
    render(
      <ColumnSeries
        items={[
          { label: 'jan/26', value: 10 },
          { label: 'fev/26', value: 20 },
          { label: 'mar/26', value: 30 },
        ]}
      />,
    )

    const labels = screen.getAllByTitle(/^(jan|fev|mar)\/26$/).map((el) => el.textContent)
    expect(labels).toEqual(['jan/26', 'fev/26', 'mar/26'])
  })

  it('expõe role="img" com aria-label listando cada item e valor', () => {
    render(
      <ColumnSeries
        items={[
          { label: 'A', value: 10 },
          { label: 'B', value: 20 },
        ]}
        valueFormatter={(v) => `${v} kWh`}
      />,
    )

    const chart = screen.getByRole('img')
    expect(chart.getAttribute('aria-label')).toBe('A: 10 kWh; B: 20 kWh')
  })

  it('calcula altura proporcional ao maior valor da série quando maxValue não é informado', () => {
    render(
      <ColumnSeries
        items={[
          { label: 'A', value: 25 },
          { label: 'B', value: 100 },
          { label: 'C', value: 50 },
        ]}
      />,
    )

    const columns = document.querySelectorAll('[data-quality]')
    const heights = Array.from(columns).map((el) => (el as HTMLElement).style.height)
    // 160px de altura útil (CHART_HEIGHT) — A a 25%, B a 100%, C a 50%.
    expect(heights).toEqual(['40px', '160px', '80px'])
  })

  it('nunca fabrica uma coluna a partir de value=null — desenha marcador tracejado de altura fixa', () => {
    render(
      <ColumnSeries
        items={[
          { label: 'A', value: null, unavailableLabel: 'sem dado' },
          { label: 'B', value: 40 },
        ]}
      />,
    )

    // Só o item com valor numérico tem `data-quality` (marcador de coluna
    // real) — o item null usa um marcador tracejado próprio, sem herdar o
    // mesmo atributo de "coluna com dado".
    expect(document.querySelectorAll('[data-quality]')).toHaveLength(1)
    expect(screen.getAllByText('sem dado').length).toBeGreaterThan(0)
    expect(screen.getByRole('img').getAttribute('aria-label')).toBe('A: sem dado; B: 40')
  })

  it('item com value=null não entra no cálculo do maior valor (maxValue implícito)', () => {
    render(
      <ColumnSeries
        items={[
          { label: 'A', value: null },
          { label: 'B', value: 40 },
        ]}
      />,
    )

    const column = document.querySelector('[data-quality]') as HTMLElement
    expect(column.style.height).toBe('160px')
  })

  it('coluna com badge é distinguível via atributo data-quality="partial", não só cor', () => {
    render(
      <ColumnSeries
        items={[
          { label: 'A', value: 10 },
          { label: 'B', value: 20, tone: 'warning', badge: { label: 'dados parciais', tone: 'warning' } },
        ]}
      />,
    )

    const columns = document.querySelectorAll('[data-quality]')
    const qualities = Array.from(columns).map((el) => el.getAttribute('data-quality'))
    expect(qualities).toEqual(['complete', 'partial'])

    // Contorno tracejado (pista de forma, não só cor) na coluna sinalizada.
    const partialColumn = columns[1] as HTMLElement
    expect(partialColumn.className).toContain('border-dashed')
    expect(columns[0].className).not.toContain('border-dashed')
  })

  it('aria-label inclui o texto do badge para o item sinalizado', () => {
    render(
      <ColumnSeries
        items={[
          { label: 'A', value: 10 },
          { label: 'B', value: 20, badge: { label: 'dados parciais', tone: 'warning' } },
        ]}
      />,
    )

    expect(screen.getByRole('img').getAttribute('aria-label')).toBe(
      'A: 10; B: 20, dados parciais',
    )
  })

  it('renderiza a legenda quando informada, com marcador tracejado para entradas dashed', () => {
    render(
      <ColumnSeries
        items={[{ label: 'A', value: 10, badge: { label: 'dados parciais', tone: 'warning' } }]}
        legend={[{ label: 'Dados parciais — dias sem telemetria coletada', tone: 'warning', dashed: true }]}
      />,
    )

    expect(
      screen.getByText('Dados parciais — dias sem telemetria coletada'),
    ).toBeInTheDocument()
  })

  it('não renderiza legenda quando a prop não é informada', () => {
    render(<ColumnSeries items={[{ label: 'A', value: 10 }]} />)

    expect(document.querySelector('ul')).not.toBeInTheDocument()
  })

  it('expõe tabela sr-only com item, valor e qualidade dos dados', () => {
    render(
      <ColumnSeries
        items={[
          { label: 'A', value: 10 },
          {
            label: 'B',
            value: 20,
            badge: { label: 'dados parciais', tone: 'warning' },
            description: '3 dias sem dado',
          },
          { label: 'C', value: null, unavailableLabel: 'sem dado' },
        ]}
        valueFormatter={(v) => `${v} kWh`}
      />,
    )

    const table = document.querySelector('table.sr-only') as HTMLElement
    expect(table).toBeInTheDocument()

    const rowA = within(table).getByText('A').closest('tr') as HTMLElement
    expect(within(rowA).getByText('10 kWh')).toBeInTheDocument()
    expect(within(rowA).getByText('completo')).toBeInTheDocument()

    const rowB = within(table).getByText('B').closest('tr') as HTMLElement
    expect(within(rowB).getByText('20 kWh')).toBeInTheDocument()
    expect(within(rowB).getByText('dados parciais — 3 dias sem dado')).toBeInTheDocument()

    const rowC = within(table).getByText('C').closest('tr') as HTMLElement
    expect(within(rowC).getByText('sem dado')).toBeInTheDocument()
  })

  it('não quebra e não renderiza gráfico quando a lista está vazia', () => {
    render(<ColumnSeries items={[]} />)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('Nenhum dado para exibir.')).toBeInTheDocument()
  })

  it('mostra o eixo Y (0/metade/máximo) com a mesma unidade do valueFormatter', () => {
    render(
      <ColumnSeries items={[{ label: 'A', value: 100 }]} valueFormatter={(v) => `${v} kWh`} />,
    )

    // Escopado à parte visual (exclui a tabela `sr-only`, que repete o mesmo
    // texto de propósito — ver comentário do `data-testid` no componente):
    // "100 kWh" aparece duas vezes aqui (tique do eixo Y no topo + valor da
    // própria coluna, que coincide com o máximo da escala neste caso).
    const visual = within(screen.getByTestId('column-series-visual'))
    expect(visual.getAllByText('100 kWh')).toHaveLength(2)
    expect(visual.getByText('50 kWh')).toBeInTheDocument()
    expect(visual.getByText('0 kWh')).toBeInTheDocument()
  })
})
