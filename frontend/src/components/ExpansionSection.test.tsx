import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { ExpansionContent } from './ExpansionSection'
import { parseExpansionAssessment } from '../lib/dashboard/expansion-contracts'

const base = {
  status: 'AMPLIAR',
  reasons: [],
  warnings: [],
  first_month: '2025-11',
  last_month: '2026-10',
  cycles_used: 12,
  imported_kwh_total: '3120',
  exported_kwh_total: '2760',
  deficit_kwh_year: '360',
  deficit_kwh_month: '30.0',
  direction: 'FALTA',
  tolerance_kwh_year: '156.0',
  balance_before_kwh: '307',
  balance_after_kwh: '0',
  installed_kwp: '3.300',
  measured_cycles: 12,
  yield_kwh_per_kwp_year: '1475',
  extra_kwp: '0.3',
  inverter_status: 'OK',
  dc_ac_ratio_after: '1.20',
  problem_months: [],
  money: {
    unavailable_reason: null,
    request_year: 2026,
    monthly_saving_first_year_brl: '21.50',
    monthly_saving_scenario_brl: '18.00',
    values_by_year: [
      { year: 2026, wire_b_share: '0.60', value_brl_kwh: '0.716684', scenario: false },
      { year: 2027, wire_b_share: '0.75', value_brl_kwh: '0.672902', scenario: false },
      { year: 2028, wire_b_share: '0.90', value_brl_kwh: '0.629121', scenario: false },
      { year: 2029, wire_b_share: '1.00', value_brl_kwh: '0.599933', scenario: true },
    ],
  },
}

function renderContent(overrides: Record<string, unknown> = {}) {
  return render(
    <MemoryRouter>
      <ExpansionContent assessment={parseExpansionAssessment({ ...base, ...overrides })} />
    </MemoryRouter>,
  )
}

describe('ExpansionContent (ADR-089)', () => {
  it('ampliar: mostra a falta, o saldo que acabou, o tamanho, o inversor e o dinheiro ano a ano', () => {
    renderContent()
    expect(screen.getByText(/deixou de cobrir em média 30 kWh por mês/)).toBeInTheDocument()
    expect(screen.getByText(/307 kWh no início do período/)).toBeInTheDocument()
    expect(screen.getByText(/cerca de 0,3 kWp/)).toBeInTheDocument()
    expect(screen.getByText(/cabe no inversor atual/)).toBeInTheDocument()
    expect(screen.getByText(/R\$\s21,50 por mês/)).toBeInTheDocument()
    expect(screen.getByText('2029+ (cenário)')).toBeInTheDocument()
    expect(screen.getByText(/Não é garantia de economia/)).toBeInTheDocument()
    // Sem botão de venda.
    expect(screen.queryByRole('button', { name: /orçamento/i })).not.toBeInTheDocument()
  })

  it('não vale: mostra a sobra em kWh positivos, sem tamanho nem dinheiro', () => {
    renderContent({
      status: 'NAO_VALE',
      deficit_kwh_year: '-720',
      deficit_kwh_month: '-60.0',
      direction: 'SOBRA',
      extra_kwp: null,
      money: null,
    })
    expect(screen.getByText(/Não vale ampliar agora/)).toBeInTheDocument()
    expect(screen.getByText(/sobram em média 60 kWh por mês/)).toBeInTheDocument()
    expect(screen.getByText('Sobra no ano')).toBeInTheDocument()
    expect(screen.queryByText(/Economia estimada/)).not.toBeInTheDocument()
  })

  it('equilibrado com sobra pequena: rótulo de sobra, não de falta', () => {
    renderContent({
      status: 'EQUILIBRADO',
      deficit_kwh_year: '-100',
      deficit_kwh_month: '-8.3',
      direction: 'SOBRA',
      extra_kwp: null,
      money: null,
    })
    expect(screen.getByText(/Geração e consumo estão próximos/)).toBeInTheDocument()
    expect(screen.getByText('Sobra no ano')).toBeInTheDocument()
    expect(screen.queryByText('Falta no ano')).not.toBeInTheDocument()
  })

  it('dinheiro indisponível explica o motivo, sem R$ inventado', () => {
    renderContent({
      money: { ...base.money, unavailable_reason: 'WIRE_B_MISSING', monthly_saving_first_year_brl: null, monthly_saving_scenario_brl: null, values_by_year: [] },
    })
    expect(screen.getByText(/não traz o Fio B/)).toBeInTheDocument()
    expect(screen.queryByText(/Economia estimada/)).not.toBeInTheDocument()
  })

  it('corrigir antes: aponta os meses com problema', () => {
    renderContent({ status: 'CORRIGIR_ANTES', problem_months: ['2026-03'] })
    expect(screen.getByText('Resolva a usina antes de ampliar')).toBeInTheDocument()
  })

  it('indisponível: diz o que falta', () => {
    renderContent({ status: 'INDISPONIVEL', reasons: ['NOT_ENOUGH_CYCLES'], cycles_used: 5 })
    expect(screen.getByText(/12 faturas confirmadas seguidas/)).toBeInTheDocument()
    expect(screen.getByText(/Temos 5/)).toBeInTheDocument()
  })

  it('sem potência cadastrada, pede o dado em vez de chutar o tamanho', () => {
    renderContent({ reasons: ['INSTALLED_POWER_UNKNOWN'], extra_kwp: null, installed_kwp: null })
    expect(screen.getByRole('link', { name: 'Minha usina' })).toBeInTheDocument()
  })
})

describe('parseExpansionAssessment', () => {
  it('recusa status desconhecido e dinheiro malformado', () => {
    expect(() => parseExpansionAssessment({ ...base, status: 'COMPRE' })).toThrow('status')
    expect(() =>
      parseExpansionAssessment({ ...base, money: { ...base.money, values_by_year: [{ year: 2026 }] } }),
    ).toThrow('money.values_by_year')
    expect(() => parseExpansionAssessment({ ...base, extra_kwp: 0.3 })).toThrow('extra_kwp')
  })

  it('aceita dinheiro nulo', () => {
    expect(parseExpansionAssessment({ ...base, money: null }).money).toBeNull()
  })
})
