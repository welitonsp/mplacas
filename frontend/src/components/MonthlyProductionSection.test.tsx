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
        cycleStart: '2026-02-15',
        cycleEnd: '2026-03-16',
        productionKwh: 1000,
        gridInjectionKwh: 400,
        gridInjectionBasis: 'METER',
        distributor: 'EQUATORIAL_GO',
        importedKwh: 210,
        selfConsumptionKwh: 600,
        quality: { missingDays: 0, provisionalDays: 0, incompleteDays: 0, unavailableDays: 0 },
      },
      {
        referenceMonth: '2026-04',
        billId: 'bill-2',
        status: 'STABLE',
        cycleStart: '2026-03-17',
        cycleEnd: '2026-04-15',
        productionKwh: 1100,
        gridInjectionKwh: 450,
        gridInjectionBasis: 'METER',
        distributor: 'EQUATORIAL_GO',
        importedKwh: 200,
        selfConsumptionKwh: 650,
        quality: { missingDays: 0, provisionalDays: 2, incompleteDays: 0, unavailableDays: 0 },
      },
      {
        referenceMonth: '2026-05',
        billId: 'bill-3',
        status: 'STABLE',
        cycleStart: '2026-04-16',
        cycleEnd: '2026-05-15',
        productionKwh: 950,
        gridInjectionKwh: 380,
        gridInjectionBasis: 'METER',
        distributor: 'EQUATORIAL_GO',
        importedKwh: 230,
        selfConsumptionKwh: 570,
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

  it('placas × medidor da Equatorial no mesmo ciclo: período da fatura, kWh das placas, kWh do medidor e o que ficou na casa (estimado)', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

    const row = screen.getByRole('heading', { level: 3, name: /mai\/26/ }).closest('li') as HTMLElement
    expect(within(row).getByText('16/04 a 15/05')).toBeInTheDocument()
    expect(within(row).getByText('Placas geraram')).toBeInTheDocument()
    expect(within(row).getByText('950 kWh')).toBeInTheDocument()
    expect(within(row).getByText('Medidor da Equatorial')).toBeInTheDocument()
    expect(within(row).getByText('380 kWh')).toBeInTheDocument()
    expect(within(row).getByText(/Ficou na casa \(estimado\)/)).toBeInTheDocument()
    expect(within(row).getByText('570 kWh')).toBeInTheDocument()
    expect(within(row).queryByText(/Não é a leitura do medidor/)).not.toBeInTheDocument()
    expect(within(row).getByText('230 kWh')).toBeInTheDocument()
  })

  it('mais recente primeiro: o ciclo da última fatura abre a lista', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

    const titles = screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)
    expect(titles[0]).toMatch(/^mai\/26/)
    expect(titles[2]).toMatch(/^mar\/26/)
  })

  it('dias sem leitura do inversor aparecem no ciclo, com quantos foram estimados pelo sol; provisório não conta', () => {
    const history = buildHistory()
    history.cycles[2] = { ...history.cycles[2], quality: { missingDays: 3, provisionalDays: 0, incompleteDays: 0, unavailableDays: 0, estimatedDays: 3 } }
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(screen.getByText('3 dias sem leitura do inversor, estimados pelo sol')).toBeInTheDocument()
    // abr/26 tem só dias provisórios: sem selo de lacuna.
    const april = screen.getByRole('heading', { level: 3, name: /abr\/26/ }).closest('li') as HTMLElement
    expect(within(april).queryByText(/sem leitura/)).not.toBeInTheDocument()
  })

  it('relatório antigo sem registro da distribuidora: diz "sem registro", nunca 0', () => {
    const history = buildHistory({
      cyclesReturned: 1,
      cycles: [
        {
          referenceMonth: '2025-01',
          billId: 'bill-old',
          status: 'STABLE',
          cycleStart: null,
          cycleEnd: null,
          productionKwh: 700,
          gridInjectionKwh: null,
          gridInjectionBasis: null,
          distributor: null,
          importedKwh: null,
          selfConsumptionKwh: null,
          quality: null,
        },
      ],
    })
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(screen.getByText('sem registro')).toBeInTheDocument()
    expect(screen.queryByText('0 kWh')).not.toBeInTheDocument()
    expect(screen.queryByText(/Ficou na casa/)).not.toBeInTheDocument()
  })

  it('produção sem dado no ciclo: "sem registro", sem barra fabricada', () => {
    const history = buildHistory()
    history.cycles[2] = { ...history.cycles[2], productionKwh: null }
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    const row = screen.getByRole('heading', { level: 3, name: /mai\/26/ }).closest('li') as HTMLElement
    expect(within(row).getByText('sem registro')).toBeInTheDocument()
  })

  it('injeção que não é do medidor (relatório antigo ou fatura sem leitura): nunca rotulada como medidor', () => {
    const history = buildHistory()
    history.cycles[2] = { ...history.cycles[2], gridInjectionBasis: 'BILL_LINE' }
    history.cycles[1] = { ...history.cycles[1], gridInjectionBasis: null }
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    for (const name of [/mai\/26/, /abr\/26/]) {
      const row = screen.getByRole('heading', { level: 3, name }).closest('li') as HTMLElement
      expect(within(row).getByText('Injeção na fatura')).toBeInTheDocument()
      expect(within(row).queryByText(/Medidor/)).not.toBeInTheDocument()
      expect(within(row).getByText(/Não é a leitura do medidor/)).toBeInTheDocument()
    }
  })

  it('distribuidora desconhecida: nome genérico, nunca inventado', () => {
    const history = buildHistory()
    history.cycles = history.cycles.map((cycle) => ({ ...cycle, distributor: 'OUTRA_SA' }))
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(screen.getAllByText('Medidor da distribuidora').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Equatorial/)).not.toBeInTheDocument()
  })

  it('com mais de 6 ciclos, mostra os 6 mais recentes e um botão para ver todos', () => {
    const base = buildHistory().cycles[0]
    const cycles = Array.from({ length: 8 }, (_, index) => ({
      ...base,
      billId: `bill-${index}`,
      referenceMonth: `2026-0${index + 1}`,
    }))
    render(<MonthlyProductionSection history={buildHistory({ cyclesReturned: 8, cycles })} plantId={PLANT_ID} />)

    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(6)
    const toggle = screen.getByRole('button', { name: 'Ver os 8 ciclos' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(8)
    expect(screen.getByRole('button', { name: 'Mostrar só os mais recentes' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('mostra mensagem neutra quando não há nenhum ciclo fechado', () => {
    render(<MonthlyProductionSection history={buildHistory({ cyclesReturned: 0, cycles: [] })} plantId={PLANT_ID} />)

    expect(screen.getByText('Sem ciclos fechados')).toBeInTheDocument()
  })

  it('mostra um estado de carregamento quando history é null', () => {
    render(<MonthlyProductionSection history={null} plantId={PLANT_ID} />)

    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument()
    expect(screen.queryByText('Sem ciclos fechados')).not.toBeInTheDocument()
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
