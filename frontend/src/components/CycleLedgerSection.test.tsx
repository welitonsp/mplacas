import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { cycleLedgerPayload, jsonResponse } from '../test/dashboardFixtures'

const fetchHistory = vi.fn()
vi.mock('../lib/api', () => ({
  fetchMonthlyProductionHistory: (...args: unknown[]) => fetchHistory(...args),
}))

import { CycleLedgerSection } from './CycleLedgerSection'

type Payload = typeof cycleLedgerPayload
const cycleOf = (over: Record<string, unknown>) => ({ ...cycleLedgerPayload.cycles[1], ...over })
const withCycles = (cycles: unknown[], window: Record<string, unknown> = {}): unknown => ({
  ...cycleLedgerPayload,
  cycles,
  savings_window: { ...cycleLedgerPayload.savings_window, ...window },
}) as Payload

function mount(payload: unknown) {
  fetchHistory.mockResolvedValue(jsonResponse(payload))
  return render(
    <MemoryRouter>
      <CycleLedgerSection plantId="plant-1" />
    </MemoryRouter>,
  )
}

async function table() {
  return screen.findByRole('table', { name: /Valor da fatura e economia estimada/ })
}

beforeEach(() => fetchHistory.mockReset())

describe('CycleLedgerSection', () => {
  it('lista os ciclos com fatura, economia "Estimada", data-base e total', async () => {
    mount(cycleLedgerPayload)
    const t = await table()
    expect(fetchHistory).toHaveBeenCalledWith('plant-1', 12)
    expect(within(t).getByRole('columnheader', { name: 'Valor da fatura' })).toBeTruthy()
    const rows = within(t).getAllByRole('row')
    // cabeçalho + 2 ciclos, o mais recente primeiro
    expect(rows).toHaveLength(3)
    expect(within(rows[1]).getByRole('rowheader').textContent).toBe('jul/26')
    expect(rows[1].textContent).toMatch(/R\$\s210,00/)
    expect(rows[1].textContent).toMatch(/R\$\s300,40\s*Estimada/)
    expect(rows[1].textContent).toContain('Calculado em 20/08/2026')
    expect(screen.getByText(/Economia estimada somada: R\$\s550,50, em 2 de 2 ciclos \(jun\/26 a jul\/26\)/)).toBeTruthy()
    expect(screen.getByText(/inclui iluminação pública e outros itens/)).toBeTruthy()
    expect(screen.queryByText(/você pagou/i)).toBeNull()
  })

  it('economia negativa aparece negativa, com a frase honesta', async () => {
    mount(withCycles([cycleOf({ estimated_savings_brl: '-42.10' })]))
    const t = await table()
    expect(t.textContent).toMatch(/-R\$\s42,10/)
    expect(t.textContent).toContain('a fatura saiu mais alta do que sairia sem a usina')
  })

  it('selos extras em texto: tarifa da fatura, parcial e fórmula antiga', async () => {
    mount(
      withCycles([
        cycleOf({ savings_tariff_source: 'BILL_TARIFF' }),
        cycleOf({ bill_id: 'x2', savings_gap_cause: 'PARTIAL_PRODUCTION' }),
        cycleOf({ bill_id: 'x3', savings_gap_cause: 'OUTDATED_CALCULATION' }),
      ]),
    )
    const t = await table()
    expect(t.textContent).toContain('Tarifa da própria fatura: pode estar subestimada')
    expect(t.textContent).toContain('Ciclo parcial, com dias sem leitura do inversor')
    expect(t.textContent).toContain('Calculada pela fórmula antiga: pode estar subestimada')
  })

  it.each([
    ['NO_PRODUCTION_DATA', 'sem produção do inversor registrada'],
    ['TARIFF_NOT_AVAILABLE', 'a fatura não trouxe a tarifa'],
    ['NO_CONSUMPTION_DATA', 'sem dado de consumo'],
    ['REPORT_PREDATES_SAVINGS', 'relatório anterior ao cálculo de economia'],
    ['SAVINGS_UNAVAILABLE', 'Economia indisponível para este ciclo'],
  ])('sem economia (%s): mostra o motivo em palavras, nunca R$ 0,00', async (reason, words) => {
    mount(withCycles([cycleOf({ estimated_savings_brl: null, savings_unavailable_reason: reason })]))
    const t = await table()
    const row = within(t).getAllByRole('row')[1]
    expect(row.textContent).toContain(words)
    expect(row.textContent).not.toMatch(/R\$\s0,00/)
    expect(row.textContent).not.toContain('Estimada')
  })

  it('fatura sem valor mostra "Valor indisponível", não R$ 0,00', async () => {
    mount(withCycles([cycleOf({ bill_total_amount_brl: null })]))
    const t = await table()
    expect(t.textContent).toContain('Valor indisponível')
    expect(t.textContent).not.toMatch(/R\$\s0,00/)
  })

  it('linhas fora da soma ficam na lista, marcadas com o motivo', async () => {
    mount(
      withCycles(
        [
          cycleOf({ reference_month: '2026-03', bill_id: 'a', is_before_commissioning: true }),
          cycleOf({ reference_month: '2026-04', bill_id: 'b', is_commissioning_month: true }),
          cycleOf({ reference_month: '2026-05', bill_id: 'c', superseded_by_rebilling: true }),
          cycleOf({ reference_month: '2026-05', bill_id: 'd' }),
        ],
        { cycles_excluded_commissioning: 2, cycles_superseded_by_rebilling: 1, cycles_without_savings: 1, cycles_in_window: 4, cycles_with_savings: 1 },
      ),
    )
    const t = await table()
    expect(within(t).getAllByRole('row')).toHaveLength(5)
    expect(t.textContent).toContain('Não entra na soma: mês anterior à ligação da usina.')
    expect(t.textContent).toContain('Não entra na soma: mês da ligação da usina (ciclo parcial).')
    expect(t.textContent).toContain('Não entra na soma: mês refaturado')
    expect(screen.getByText(/Ficaram fora da soma: 2 ciclos do mês da ligação.*1 cálculo de mês refaturado.*1 ciclo sem economia calculada/)).toBeTruthy()
  })

  it('total nulo: diz que nenhum ciclo tem economia, sem R$ na linha', async () => {
    mount(
      withCycles([cycleOf({ estimated_savings_brl: null, savings_unavailable_reason: 'NO_PRODUCTION_DATA' })], {
        total_estimated_savings_brl: null,
        cycles_with_savings: 0,
        cycles_without_savings: 1,
        cycles_in_window: 1,
        first_reference_month: null,
        last_reference_month: null,
      }),
    )
    await table()
    const line = screen.getByText(/Nenhum ciclo do período tem economia calculada/)
    expect(line.textContent).not.toMatch(/R\$/)
    expect(screen.queryByText(/Economia estimada somada/)).toBeNull()
  })

  it('sem data de ligação: avisa e aponta para Minha usina', async () => {
    mount(withCycles([cycleOf({})], { commissioning_known: false }))
    await table()
    expect(screen.getByText(/não tem data de ligação cadastrada/)).toBeTruthy()
    const link = screen.getByRole('link', { name: 'Minha usina' })
    expect(link.getAttribute('href')).toMatch(/\/dashboard\//)
  })

  it('com data de ligação conhecida e sem exclusões, não mostra avisos extras', async () => {
    mount(cycleLedgerPayload)
    await table()
    expect(screen.queryByText(/não tem data de ligação/)).toBeNull()
    expect(screen.queryByText(/Ficaram fora da soma/)).toBeNull()
  })

  it('API antiga (sem campos novos): tudo indisponível, sem R$ 0,00 e sem total', async () => {
    mount({ cycles: [{ reference_month: '2026-05', bill_id: 'old' }] })
    const t = await table()
    expect(t.textContent).toContain('ainda não informada por esta versão do servidor')
    expect(t.textContent).not.toMatch(/R\$\s0,00/)
    expect(screen.getByText(/Soma indisponível/)).toBeTruthy()
  })

  it('vazio: aponta para o envio de fatura na mesma aba', async () => {
    mount({ ...cycleLedgerPayload, cycles: [], cycles_returned: 0 })
    await screen.findByText('Nenhuma fatura confirmada ainda')
    expect(screen.getByRole('link', { name: 'Importar uma fatura' }).getAttribute('href')).toBe('#faturas')
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('carregando: esqueleto e anúncio; depois conteúdo', async () => {
    let release: (r: Response) => void = () => {}
    fetchHistory.mockReturnValue(new Promise<Response>((resolve) => (release = resolve)))
    const { container } = render(
      <MemoryRouter>
        <CycleLedgerSection plantId="plant-1" />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 2, name: 'A conta, ciclo a ciclo' })).toBeTruthy()
    expect(container.textContent).toContain('Carregando a conta de cada ciclo.')
    expect(screen.queryByRole('table')).toBeNull()
    release(jsonResponse(cycleLedgerPayload))
    await table()
    expect(container.textContent).not.toContain('Carregando a conta')
  })

  it('erro: mensagem e "tentar de novo" refaz a leitura', async () => {
    fetchHistory.mockResolvedValueOnce(jsonResponse({}, 500))
    render(
      <MemoryRouter>
        <CycleLedgerSection plantId="plant-1" />
      </MemoryRouter>,
    )
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('Erro ao buscar a conta de cada ciclo.')
    fetchHistory.mockResolvedValue(jsonResponse(cycleLedgerPayload))
    fireEvent.click(within(alert).getByRole('button'))
    await table()
    await waitFor(() => expect(fetchHistory).toHaveBeenCalledTimes(2))
  })
})
