import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { MonthlyProductionCycle, MonthlyProductionHistoryResponse, UtilityCheck } from '../lib/dashboard/monthly-history-contracts'
import { MonthlyProductionSection } from './MonthlyProductionSection'
import * as api from '../lib/api'

const PLANT_ID = '11111111-1111-1111-1111-111111111111'

function okCheck(overrides: Partial<UtilityCheck> = {}): UtilityCheck {
  return {
    verdict: 'OK',
    missingCreditsKwh: 0,
    creditsAvailableKwh: 255.98,
    creditsUsedKwh: 255.98,
    creditBalanceKwh: 0,
    meterExportKwh: 238,
    previousBalanceKwh: 17.98,
    exportSharePercent: 40,
    exportShareBaselinePercent: null,
    reasons: [],
    ...overrides,
  }
}

function cycle(overrides: Partial<MonthlyProductionCycle>): MonthlyProductionCycle {
  return {
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
    utilityCheck: okCheck(),
    ...overrides,
  }
}

function buildHistory(
  overrides: Partial<MonthlyProductionHistoryResponse> = {}
): MonthlyProductionHistoryResponse {
  return {
    plantId: PLANT_ID,
    limit: 12,
    cyclesReturned: 3,
    cycles: [
      cycle({}),
      cycle({
        referenceMonth: '2026-04',
        billId: 'bill-2',
        cycleStart: '2026-03-17',
        cycleEnd: '2026-04-15',
        productionKwh: 1100,
        gridInjectionKwh: 450,
        selfConsumptionKwh: 650,
        quality: { missingDays: 0, provisionalDays: 2, incompleteDays: 0, unavailableDays: 0 },
      }),
      cycle({
        referenceMonth: '2026-05',
        billId: 'bill-3',
        cycleStart: '2026-04-16',
        cycleEnd: '2026-05-15',
        productionKwh: 950,
        gridInjectionKwh: 380,
        selfConsumptionKwh: 570,
        quality: { missingDays: 3, provisionalDays: 0, incompleteDays: 0, unavailableDays: 0 },
      }),
    ],
    ...overrides,
  }
}

function row(name: RegExp): HTMLElement {
  return screen.getByRole('heading', { level: 3, name }).closest('li') as HTMLElement
}

describe('MonthlyProductionSection', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('cada ciclo: período da fatura, produção, rede pelo medidor e casa estimada, com o veredito e a prova dos créditos', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

    const may = row(/mai\/26/)
    expect(within(may).getByText('16/04 a 15/05')).toBeInTheDocument()
    expect(within(may).getByText('Produziu')).toBeInTheDocument()
    expect(within(may).getByText('950 kWh')).toBeInTheDocument()
    expect(within(may).getByText('medidor Equatorial')).toBeInTheDocument()
    expect(within(may).getByText('380 kWh')).toBeInTheDocument()
    expect(within(may).getByText('Casa')).toBeInTheDocument()
    expect(within(may).getByText('570 kWh')).toBeInTheDocument()
    expect(within(may).getByText('estimado')).toBeInTheDocument()
    expect(within(may).getByText('Sem sinal de prejuízo')).toBeInTheDocument()
    expect(within(may).getByText(/Todo kWh registrado virou crédito: 238 kWh registrados \+ 17,98 kWh de saldo anterior; 255,98 kWh usados e saldo de 0 kWh/)).toBeInTheDocument()
  })

  it('resumo no topo: sem prejuízo quando todos os ciclos conferidos fecham', () => {
    render(<MonthlyProductionSection history={buildHistory()} plantId={PLANT_ID} />)

    expect(screen.getAllByText('Sem sinal de prejuízo').length).toBeGreaterThan(1)
    expect(screen.getByText('Conferimos 3 ciclos: todo kWh que a Equatorial registrou virou crédito.')).toBeInTheDocument()
  })

  it('créditos faltando: resumo e ciclo acusam prejuízo comprovado, com os kWh', () => {
    const history = buildHistory()
    history.cycles[2] = { ...history.cycles[2], utilityCheck: okCheck({ verdict: 'LOSS', missingCreditsKwh: 15.98, reasons: ['CREDITS_MISSING'] }) }
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(screen.getByText('15,98 kWh de créditos sem explicação')).toBeInTheDocument()
    expect(within(row(/mai\/26/)).getByText('Créditos faltando')).toBeInTheDocument()
    expect(within(row(/mai\/26/)).getByText(/não mostra 15,98 kWh nem como abatimento nem como saldo/)).toBeInTheDocument()
  })

  it('envio maior que a produção: registro impossível, com pedido de aferição', () => {
    const history = buildHistory()
    history.cycles[2] = { ...history.cycles[2], gridInjectionKwh: 1200, utilityCheck: okCheck({ verdict: 'IMPOSSIBLE', reasons: ['IMPOSSIBLE_EXPORT'] }) }
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(within(row(/mai\/26/)).getByText('Registro impossível')).toBeInTheDocument()
    expect(within(row(/mai\/26/)).getByText(/registrou 238 kWh enviados à rede/)).toBeInTheDocument()
    expect(within(row(/mai\/26/)).getByText(/vale pedir aferição/)).toBeInTheDocument()
  })

  it('fração enviada fora do padrão: suspeita com as duas hipóteses, nunca prova', () => {
    const history = buildHistory()
    history.cycles[2] = {
      ...history.cycles[2],
      utilityCheck: okCheck({ verdict: 'SUSPECT', exportSharePercent: 17, exportShareBaselinePercent: 45, reasons: ['EXPORT_SHARE_DROP'] }),
    }
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(screen.getByText('Ciclo fora do padrão')).toBeInTheDocument()
    expect(within(row(/mai\/26/)).getByText(/Só 17% da produção foi para a rede, contra 45% no seu histórico\. Pode ser o medidor ou mais consumo durante o dia\./)).toBeInTheDocument()
  })

  it('sem conferência (sem leitura do medidor ou backend antigo): diz o motivo, nunca "sem prejuízo"', () => {
    const history = buildHistory({
      cyclesReturned: 2,
      cycles: [
        cycle({ utilityCheck: okCheck({ verdict: 'UNVERIFIABLE', reasons: ['NO_METER_READING'] }) }),
        cycle({ referenceMonth: '2026-04', billId: 'bill-2', utilityCheck: null }),
      ],
    })
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(screen.queryByText('Sem sinal de prejuízo')).not.toBeInTheDocument()
    expect(screen.getByText('Ainda sem conferência')).toBeInTheDocument()
    expect(within(row(/mar\/26/)).getByText('A fatura deste ciclo não traz a leitura do medidor de geração.')).toBeInTheDocument()
    expect(within(row(/abr\/26/)).getByText('Conferência ainda não disponível para este ciclo.')).toBeInTheDocument()
  })

  it('janela parcial: nunca verde "sem sinal de prejuízo" se algum ciclo ficou sem conferência', () => {
    const history = buildHistory()
    history.cycles[2] = { ...history.cycles[2], utilityCheck: okCheck({ verdict: 'UNVERIFIABLE', reasons: ['CREDITS_UNBALANCED'] }) }
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(screen.getByText('Sem prejuízo nos 2 ciclos conferidos')).toBeInTheDocument()
    expect(screen.getByText(/2 de 3 ciclos conferidos/)).toBeInTheDocument()
    expect(within(row(/mai\/26/)).getByText(/passam do que havia/)).toBeInTheDocument()
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
    expect(within(row(/abr\/26/)).queryByText(/sem leitura/)).not.toBeInTheDocument()
  })

  it('relatório antigo sem registro da distribuidora: "sem registro", nunca 0', () => {
    const history = buildHistory({
      cyclesReturned: 1,
      cycles: [
        cycle({
          referenceMonth: '2025-01',
          billId: 'bill-old',
          cycleStart: null,
          cycleEnd: null,
          productionKwh: 700,
          gridInjectionKwh: null,
          gridInjectionBasis: null,
          distributor: null,
          importedKwh: null,
          selfConsumptionKwh: null,
          quality: null,
          utilityCheck: null,
        }),
      ],
    })
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(screen.getAllByText('sem registro')).toHaveLength(2)
    expect(screen.queryByText('0 kWh')).not.toBeInTheDocument()
  })

  it('injeção que não é do medidor: rotulada como linha da fatura, com aviso, nunca como medidor', () => {
    const history = buildHistory()
    history.cycles[2] = { ...history.cycles[2], gridInjectionBasis: 'BILL_LINE' }
    history.cycles[1] = { ...history.cycles[1], gridInjectionBasis: null }
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    for (const name of [/mai\/26/, /abr\/26/]) {
      expect(within(row(name)).getByText('linha da fatura')).toBeInTheDocument()
      expect(within(row(name)).queryByText(/medidor Equatorial/)).not.toBeInTheDocument()
      expect(within(row(name)).getByText(/não é a leitura do medidor/)).toBeInTheDocument()
    }
  })

  it('distribuidora desconhecida: nome genérico, nunca inventado', () => {
    const history = buildHistory()
    history.cycles = history.cycles.map((item) => ({ ...item, distributor: 'OUTRA_SA' }))
    render(<MonthlyProductionSection history={history} plantId={PLANT_ID} />)

    expect(screen.getAllByText('medidor distribuidora').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Equatorial/)).not.toBeInTheDocument()
  })

  it('com mais de 6 ciclos, mostra os 6 mais recentes e um botão para ver todos', () => {
    const cycles = Array.from({ length: 8 }, (_, index) => cycle({ billId: `bill-${index}`, referenceMonth: `2026-0${index + 1}` }))
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
