import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { MonthlyProductionHistoryResponse } from '../lib/dashboard/monthly-history-contracts'
import { MonthlyProductionSection } from './MonthlyProductionSection'
import * as api from '../lib/api'

const PLANT_ID = '11111111-1111-1111-1111-111111111111'

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
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renderiza uma coluna por ciclo, em ordem cronológica (leitura esquerda→direita), com rótulo e valor em kWh', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

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
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

    const ariaLabel = screen.getByRole('img').getAttribute('aria-label') ?? ''
    expect(ariaLabel).toContain('mar/26: 1.000 kWh')
    expect(ariaLabel).toContain('abr/26: 1.100 kWh')
    expect(ariaLabel).toContain('mai/26: 950 kWh')
  })

  it('mostra o selo de dados parciais só no ciclo com missingDays/unavailableDays > 0', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

    // Só o ciclo de mai/26 (missingDays: 3) tem a lacuna que dispara o selo.
    expect(screen.getAllByText('dados parciais')).toHaveLength(1)
  })

  it('ciclo parcial é distinguível via atributo (data-quality), não só visualmente', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

    const columns = document.querySelectorAll('[data-quality]')
    expect(columns).toHaveLength(3)
    const qualities = Array.from(columns).map((el) => el.getAttribute('data-quality'))
    // mar/26 e abr/26 completos, mai/26 parcial — mesma ordem cronológica.
    expect(qualities).toEqual(['complete', 'complete', 'partial'])
  })

  it('o aria-label do gráfico marca o ciclo parcial explicitamente (não só a cor da coluna)', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

    const chart = screen.getByRole('img')
    expect(chart.getAttribute('aria-label')).toContain('mai/26: 950 kWh, dados parciais')
  })

  it('mostra a contagem exata de dias sem dado do ciclo parcial, nunca só em tooltip', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

    // Texto visível abaixo da coluna (não aria-hidden em ancestral direto
    // marcado, mas parte do DOM real e consultável por `getByText`).
    expect(screen.getByText('3 dias sem dado')).toBeInTheDocument()
  })

  it('exibe uma entrada de legenda explicando o selo "dados parciais" quando há ao menos um ciclo com lacuna', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

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
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(
      screen.queryByText('Dados parciais — dias sem telemetria coletada')
    ).not.toBeInTheDocument()
  })

  it('expõe uma tabela sr-only com ciclo, valor e qualidade dos dados por linha', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

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
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

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
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(screen.getAllByText('sem dado').length).toBeGreaterThan(0)
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'mai/26: sem dado')
  })

  it('mostra mensagem neutra quando não há nenhum ciclo fechado', () => {
    render(<MonthlyProductionSection history={buildHistory({ cyclesReturned: 0, cycles: [] })} plantId={PLANT_ID} />)

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
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(
      within(screen.getByTestId('column-series-visual')).getByText('mai/26')
    ).toBeInTheDocument()
    expect(
      screen.getByText('Comparação disponível a partir do segundo ciclo fechado.')
    ).toBeInTheDocument()
  })

  it('mostra um estado de carregamento (sem gráfico) quando history é null', () => {
    render(<MonthlyProductionSection history={null} plantId={PLANT_ID} />)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(
      screen.queryByText('Ainda não há ciclo de faturamento fechado para esta usina.')
    ).not.toBeInTheDocument()
  })

  describe('exportação do relatório mensal', () => {
    it('não mostra o controle de exportação quando não há ciclo fechado', () => {
      render(<MonthlyProductionSection history={buildHistory({ cyclesReturned: 0, cycles: [] })} plantId={PLANT_ID} />)

      expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    })

    it('exporta em PDF por padrão e permite trocar de formato antes de baixar', async () => {
      const downloadSpy = vi.spyOn(api, 'downloadMonthlyReportExport').mockResolvedValue(undefined)
      render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

      fireEvent.click(screen.getByRole('button', { name: /baixar pdf/i }))
      await waitFor(() => expect(downloadSpy).toHaveBeenCalledWith(PLANT_ID, 'pdf'))

      fireEvent.change(screen.getByLabelText(/exportar relatório do ciclo mais recente/i), {
        target: { value: 'xlsx' },
      })
      fireEvent.click(screen.getByRole('button', { name: /baixar xlsx/i }))
      await waitFor(() => expect(downloadSpy).toHaveBeenLastCalledWith(PLANT_ID, 'xlsx'))

      expect(downloadSpy).toHaveBeenCalledTimes(2)
    })

    it('desabilita o botão e mostra "Gerando..." enquanto o download está em andamento', async () => {
      let resolveDownload: () => void = () => {}
      vi.spyOn(api, 'downloadMonthlyReportExport').mockImplementation(
        () => new Promise((resolve) => { resolveDownload = () => resolve(undefined) })
      )
      render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

      const button = screen.getByRole('button', { name: /baixar pdf/i })
      fireEvent.click(button)

      expect(await screen.findByRole('button', { name: /gerando pdf/i })).toBeDisabled()

      resolveDownload()
      await waitFor(() => expect(screen.getByRole('button', { name: /baixar pdf/i })).not.toBeDisabled())
    })

    it('anuncia o carregamento por uma live region "polite" separada do botão, e volta a ficar em silêncio ao terminar (T10)', async () => {
      let resolveDownload: () => void = () => {}
      vi.spyOn(api, 'downloadMonthlyReportExport').mockImplementation(
        () => new Promise((resolve) => { resolveDownload = () => resolve(undefined) })
      )
      const { container } = render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

      const liveRegion = container.querySelector('[aria-live="polite"]') as HTMLElement
      expect(liveRegion).toBeInTheDocument()
      expect(liveRegion).toHaveTextContent('')

      const button = screen.getByRole('button', { name: /baixar pdf/i })
      expect(button).toHaveAttribute('aria-busy', 'false')
      fireEvent.click(button)

      await waitFor(() => expect(liveRegion).toHaveTextContent('Gerando arquivo PDF, aguarde.'))
      expect(screen.getByRole('button', { name: /gerando pdf/i })).toHaveAttribute('aria-busy', 'true')

      resolveDownload()
      await waitFor(() => expect(liveRegion).toHaveTextContent(''))
    })

    it('o <select> de formato tem alvo de toque mínimo de 44px (T10)', () => {
      render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

      expect(screen.getByLabelText(/exportar relatório do ciclo mais recente/i).className).toMatch(
        /min-h-\[44px\]/
      )
    })

    it('mostra mensagem de erro quando o backend não consegue gerar o relatório, sem travar a UI', async () => {
      vi.spyOn(api, 'downloadMonthlyReportExport').mockRejectedValue(
        new Error('Não foi possível gerar o relatório (500).')
      )
      render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

      fireEvent.click(screen.getByRole('button', { name: /baixar pdf/i }))

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Não foi possível gerar o relatório (500).'
      )
      // A UI volta a permitir nova tentativa — não trava no estado de erro.
      expect(screen.getByRole('button', { name: /baixar pdf/i })).not.toBeDisabled()
    })

    it('limpa o erro anterior ao tentar exportar novamente', async () => {
      const downloadSpy = vi
        .spyOn(api, 'downloadMonthlyReportExport')
        .mockRejectedValueOnce(new Error('Falha temporária.'))
        .mockResolvedValueOnce(undefined)
      render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

      fireEvent.click(screen.getByRole('button', { name: /baixar pdf/i }))
      expect(await screen.findByRole('alert')).toHaveTextContent('Falha temporária.')

      fireEvent.click(screen.getByRole('button', { name: /baixar pdf/i }))
      await waitFor(() => expect(downloadSpy).toHaveBeenCalledTimes(2))
      await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    })
  })
})
