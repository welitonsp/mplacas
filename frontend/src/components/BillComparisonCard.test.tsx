import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { BillComparisonCard } from './BillComparisonCard'
import type { ExecutiveIndicators } from '../lib/dashboard/contracts'

const base: ExecutiveIndicators = {
  cycle_production_kwh: '400.000',
  imported_kwh: '221',
  injected_kwh: '235',
  estimated_self_consumption_kwh: '165.000',
  estimated_total_consumption_kwh: '386.000',
  self_consumption_rate_percent: '41.3',
  self_sufficiency_rate_percent: '42.7',
  grid_dependency_rate_percent: '57.3',
  exported_generation_rate_percent: '58.8',
  credit_coverage_rate_percent: '100.0',
  bill_energy_component_brl: '40.01',
  health_score: 100,
  total_amount_brl: '70.22',
  public_lighting_brl: '30.21',
  tariff_with_taxes_brl_kwh: '0.787589',
  tariff_without_taxes_brl_kwh: '0.613030',
  credit_balance_kwh: '17.98',
  estimated_savings_brl: '264.00',
  savings_unavailable_reason: null,
  compensated_kwh: '221',
  excess_credit_kwh: '14.000',
  bill_without_solar_brl: '334.22',
  credit_balance_value_brl: '11.01',
  modeled_bill_brl: '68.91',
  bill_model_difference_brl: '1.31',
}

function detail(label: string) {
  const term = screen.getByText(label)
  return term.parentElement as HTMLElement
}

describe('BillComparisonCard', () => {
  it('diz que a conta sem a usina usa a tarifa cheia da distribuidora, com o valor', () => {
    render(
      <BillComparisonCard
        indicators={{ ...base, savings_tariff_brl_kwh: '1.145751', savings_tariff_source: 'DISTRIBUTOR_FULL_TARIFF' }}
        referenceMonth="2026-09"
      />,
    )
    expect(screen.getByText('Com a tarifa cheia da distribuidora: R$ 1,146/kWh com impostos')).toBeInTheDocument()
  })

  it('sem a origem da tarifa (backend antigo), não afirma nada sobre ela', () => {
    render(<BillComparisonCard indicators={base} referenceMonth="2026-09" />)
    expect(screen.queryByText(/tarifa/i)).not.toBeInTheDocument()
  })

  it('avisa quando a tarifa cheia faltou e a economia pode estar subestimada', () => {
    render(
      <BillComparisonCard
        indicators={{ ...base, savings_tariff_brl_kwh: '0.787589', savings_tariff_source: 'BILL_TARIFF' }}
        referenceMonth="2026-09"
      />,
    )
    expect(screen.getByText('Com a tarifa da própria fatura: pode subestimar a economia')).toBeInTheDocument()
  })

  it('mostra quanto pagaria sem a usina, quanto pagou e a economia, com os números do backend', () => {
    render(<BillComparisonCard indicators={base} referenceMonth="2026-09" />)

    expect(screen.getByRole('heading', { name: 'Sua conta com e sem a usina' })).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*264,00/)).toBeInTheDocument()
    expect(screen.getByText('Sem a usina, você pagaria').nextElementSibling?.textContent).toMatch(/334,22/)
    expect(screen.getByText('Com a usina, você pagou').nextElementSibling?.textContent).toMatch(/70,22/)
    expect(within(detail('Energia que saiu para a rede')).getByText(/14 kWh passaram do consumo/)).toBeInTheDocument()
    expect(within(detail('Créditos guardados')).getByText(/11,01/)).toBeInTheDocument()
    expect(within(detail('Conferência com a fatura')).getByText(/1,31 de outros itens/)).toBeInTheDocument()
  })

  it('diferença de centavos aparece como "confere com o valor cobrado"', () => {
    render(<BillComparisonCard indicators={{ ...base, bill_model_difference_brl: '0.02' }} referenceMonth="2026-09" />)
    expect(within(detail('Conferência com a fatura')).getByText('Confere com o valor cobrado')).toBeInTheDocument()
  })

  it('sem tarifa (campos null) o card não aparece — nada de R$ 0,00 fabricado', () => {
    const { container } = render(
      <BillComparisonCard
        indicators={{ ...base, bill_without_solar_brl: null, estimated_savings_brl: null }}
        referenceMonth="2026-09"
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('backend antigo, sem os campos novos: não aparece', () => {
    const legacy = { ...base }
    delete legacy.bill_without_solar_brl
    const { container } = render(<BillComparisonCard indicators={legacy} referenceMonth="2026-09" />)
    expect(container).toBeEmptyDOMElement()
  })
})
