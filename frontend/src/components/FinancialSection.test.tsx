import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import type { ExecutiveIndicators } from '../lib/dashboard/contracts'
import type { FinancialReturnResponse } from '../lib/dashboard/financial-return-contracts'
import type { PlantResource } from '../hooks/usePlantResource'
import { FinancialSection } from './FinancialSection'

// Mesmos valores de `dashboardFixtures.ts::executivePayload.current_cycle.indicators`
// (Etapa 7 — extração de `FinancialSection`): consistente com a fórmula real do
// backend, bill_energy_component_brl = total_amount_brl - public_lighting_brl
// (ver intelligence/energy_engine.py::analyze_energy_cycle) — 420,71 - 30,21.
function buildIndicators(overrides: Partial<ExecutiveIndicators> = {}): ExecutiveIndicators {
  return {
    cycle_production_kwh: 500,
    imported_kwh: 120,
    injected_kwh: 80,
    estimated_self_consumption_kwh: 420,
    estimated_total_consumption_kwh: 540,
    self_consumption_rate_percent: 84,
    self_sufficiency_rate_percent: 77.7,
    grid_dependency_rate_percent: 22.3,
    exported_generation_rate_percent: 16,
    credit_coverage_rate_percent: 100,
    bill_energy_component_brl: 390.5,
    health_score: 70,
    total_amount_brl: 420.71,
    public_lighting_brl: 30.21,
    tariff_with_taxes_brl_kwh: 0.85,
    tariff_without_taxes_brl_kwh: 0.6,
    credit_balance_kwh: 63.98,
    estimated_savings_brl: 120.4,
    savings_unavailable_reason: null,
    ...overrides,
  }
}

function buildFinancialReturn(
  overrides: Partial<PlantResource<FinancialReturnResponse>> = {}
): PlantResource<FinancialReturnResponse> {
  return {
    data: {
      plant_id: 'plant-1',
      investment_amount_brl: null,
      investment_recorded_on: null,
      commissioned_on: null,
      accumulated_savings_brl: null,
      average_monthly_savings_brl: null,
      cycles_counted: null,
      cycles_expected: null,
      roi_percent: null,
      payback_projection_months: null,
      unavailable_reason: 'INVESTMENT_NOT_REGISTERED',
      payback_unavailable_reason: 'INVESTMENT_NOT_REGISTERED',
    },
    status: 'success',
    error: null,
    lastUpdated: new Date('2026-08-01T00:00:00Z'),
    refetch: vi.fn(),
    ...overrides,
  }
}

describe('FinancialSection', () => {
  it('ordem da aba Dinheiro: conta com e sem a usina primeiro; sem investimento cadastrado, nenhuma seção de retorno (o pedido fica no painel Usina × CDI)', () => {
    render(
      <FinancialSection
        indicators={buildIndicators({ bill_without_solar_brl: 540.11, compensated_kwh: 90 })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )

    const headings = screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent)
    expect(headings).toEqual(['Sua conta com e sem a usina'])
    for (const removed of ['Resumo financeiro', 'Custo do ciclo', 'Créditos de energia', 'Cobertura por créditos']) {
      expect(screen.queryByText(removed)).not.toBeInTheDocument()
    }
    expect(screen.queryByText(/Decisão financeira/)).not.toBeInTheDocument()
    expect(screen.getByText('Detalhes da fatura de jul/26').closest('details')).not.toBeNull()
  })

  it('"Pago com créditos": percentual do motor e kWh compensados de kWh da rede; abaixo de 100% diz que o restante foi sem crédito', () => {
    render(
      <FinancialSection
        indicators={buildIndicators({
          bill_without_solar_brl: 540.11,
          credit_coverage_rate_percent: 75,
          compensated_kwh: 90,
          imported_kwh: 120,
        })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )

    expect(screen.getByText('Pago com créditos')).toBeInTheDocument()
    expect(screen.getByText('75% da energia da rede')).toBeInTheDocument()
    expect(screen.getByText('90 de 120 kWh. O restante foi cobrado sem crédito.')).toBeInTheDocument()
  })

  it('"Pago com créditos" com 1 casa: 99,7% não vira 100% ao lado de "o restante"', () => {
    render(
      <FinancialSection
        indicators={buildIndicators({ bill_without_solar_brl: 540.11, credit_coverage_rate_percent: 99.7, compensated_kwh: 337, imported_kwh: 338 })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )

    expect(screen.getByText('99,7% da energia da rede')).toBeInTheDocument()
    expect(screen.getByText('337 de 338 kWh. O restante foi cobrado sem crédito.')).toBeInTheDocument()
  })

  it('100% coberto: sem a frase do restante; sem energia da rede: sem a linha', () => {
    const { unmount } = render(
      <FinancialSection
        indicators={buildIndicators({ bill_without_solar_brl: 540.11, credit_coverage_rate_percent: 100, compensated_kwh: 120, imported_kwh: 120 })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )
    expect(screen.getByText('120 de 120 kWh.')).toBeInTheDocument()
    expect(screen.queryByText(/restante/)).not.toBeInTheDocument()
    unmount()

    render(
      <FinancialSection
        indicators={buildIndicators({ bill_without_solar_brl: 540.11, credit_coverage_rate_percent: 0, compensated_kwh: 0, imported_kwh: 0 })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )
    expect(screen.queryByText('Pago com créditos')).not.toBeInTheDocument()
  })

  it('detalhes da fatura: decomposição e tarifa impressa com 3 casas; a nota diz o que a conta "sem a usina" usou, pelo motor', () => {
    render(
      <FinancialSection
        indicators={buildIndicators({
          bill_without_solar_brl: 540.11,
          tariff_with_taxes_brl_kwh: 0.787589,
          tariff_without_taxes_brl_kwh: 0.61303,
          savings_tariff_source: 'DISTRIBUTOR_FULL_TARIFF',
          savings_tariff_brl_kwh: 1.146179,
        })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )

    const details = screen.getByText('Detalhes da fatura de jul/26').closest('details') as HTMLElement
    const billBar = within(details).getByRole('img', { name: /Total R\$\s*420,71/ })
    expect(billBar.getAttribute('aria-label')).toMatch(/Energia e encargos R\$\s*390,50/)
    expect(billBar.getAttribute('aria-label')).toMatch(/Iluminação pública R\$\s*30,21/)

    expect(within(details).getByText('Tarifa impressa na fatura')).toBeInTheDocument()
    expect(within(details).getByText('R$ 0,788/kWh com impostos')).toBeInTheDocument()
    expect(within(details).getByText('R$ 0,613/kWh sem impostos')).toBeInTheDocument()
    expect(within(details).queryByText(/0,787589/)).not.toBeInTheDocument()
    expect(within(details).queryByText(/SCEE/)).not.toBeInTheDocument()
    expect(
      within(details).getByText(
        'A conta “sem a usina” não usa esta tarifa: usa a tarifa cheia da distribuidora, R$ 1,146/kWh com impostos, que é o que você pagaria sem créditos.',
      ),
    ).toBeInTheDocument()
  })

  it('detalhes: bandeira incluída na conta "sem a usina" e créditos que não vêm da usina fora da economia (ADR-085)', () => {
    render(
      <FinancialSection
        indicators={buildIndicators({
          tariff_with_taxes_brl_kwh: 0.787884,
          tariff_without_taxes_brl_kwh: 0.61303,
          flag_tariff_brl_kwh: 0.011721,
          non_energy_credits_brl: 30.38,
        })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )

    const details = screen.getByText('Detalhes da fatura de jul/26').closest('details') as HTMLElement
    expect(within(details).getByText(/Bandeira tarifária do ciclo \(R\$ 0,012\/kWh com impostos\) incluída/)).toBeInTheDocument()
    expect(within(details).getByText(/R\$\s*30,38 de créditos da fatura que não vêm da usina/)).toBeInTheDocument()
  })

  it('classe tarifária: lida, presumida (fatura antiga) e não identificada (ADR-087)', () => {
    const cases: Array<[Record<string, unknown>, RegExp]> = [
      [{ tariff_class: 'B1_RESIDENCIAL_CONVENCIONAL', tariff_class_presumed: false }, /Classe tarifária lida da fatura: B1 residencial convencional\./],
      [{ tariff_class: 'B1_RESIDENCIAL_CONVENCIONAL', tariff_class_presumed: true }, /Classe tarifária presumida: B1 residencial convencional\..*reimporte o PDF/],
      [{ tariff_class: 'NAO_IDENTIFICADA', tariff_class_presumed: false }, /Classe tarifária não identificada na fatura/],
      [
        { tariff_class: 'B1_RESIDENCIAL_BRANCA', tariff_class_presumed: false, savings_tariff_source: 'BILL_TARIFF' },
        /lida da fatura: B1 residencial, tarifa branca\. Não há tarifa homologada cadastrada para essa classe em todo o período/,
      ],
    ]
    for (const [extra, text] of cases) {
      const { unmount } = render(
        <FinancialSection
          indicators={buildIndicators({ tariff_with_taxes_brl_kwh: 0.787884, tariff_without_taxes_brl_kwh: 0.61303, ...extra })}
          referenceMonth="2026-07"
          financialReturn={buildFinancialReturn()}
          />
      )
      expect(screen.getByText(text)).toBeInTheDocument()
      unmount()
    }
  })

  it('sem bandeira nem créditos externos: nenhuma linha extra', () => {
    render(
      <FinancialSection
        indicators={buildIndicators({ tariff_with_taxes_brl_kwh: 0.787884, tariff_without_taxes_brl_kwh: 0.61303 })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )
    expect(screen.queryByText(/Bandeira tarifária do ciclo/)).not.toBeInTheDocument()
    expect(screen.queryByText(/não vêm da usina/)).not.toBeInTheDocument()
  })

  it('tarifa da própria fatura (BILL_TARIFF): a nota avisa que pode subestimar; sem o campo, não afirma nada', () => {
    const { unmount } = render(
      <FinancialSection
        indicators={buildIndicators({ bill_without_solar_brl: 540.11, savings_tariff_source: 'BILL_TARIFF' })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )
    expect(screen.getByText(/usa esta tarifa da própria fatura e, por isso, pode subestimar a economia/)).toBeInTheDocument()
    unmount()

    render(
      <FinancialSection
        indicators={buildIndicators({ bill_without_solar_brl: 540.11 })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )
    expect(screen.queryByText(/A conta “sem a usina”/)).not.toBeInTheDocument()
  })

  it('backend sem a conta "sem a usina": mostra a economia estimada sozinha, sem sumir', () => {
    render(
      <FinancialSection
        indicators={buildIndicators()}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )

    const heading = screen.getByRole('heading', { level: 2, name: 'Economia em jul/26' })
    const section = heading.closest('section') as HTMLElement
    expect(within(section).getByText(/R\$\s*120,40/)).toBeInTheDocument()
    expect(within(section).getByText('Estimado')).toBeInTheDocument()
    // Saldo e cobertura não somem quando a conta do ciclo não aparece.
    expect(within(section).getByText('Créditos guardados')).toBeInTheDocument()
    expect(within(section).getByText('63,98 kWh')).toBeInTheDocument()
    expect(within(section).getByText('100% da energia da rede')).toBeInTheDocument()
  })

  it('nunca mostra R$ 0,00 de economia quando a fatura não tem tarifa registrada — mostra mensagem explícita', () => {
    render(
      <FinancialSection
        indicators={buildIndicators({
          tariff_with_taxes_brl_kwh: null,
          tariff_without_taxes_brl_kwh: null,
          estimated_savings_brl: null,
          savings_unavailable_reason: 'TARIFF_NOT_AVAILABLE',
        })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
      />
    )

    const savingsMessage = screen.getByText(/fatura deste ciclo não tem a tarifa com impostos registrada/)
    const savingsCard = savingsMessage.closest('div') as HTMLElement

    expect(within(savingsCard).queryByText(/R\$\s*0,00/)).not.toBeInTheDocument()
    expect(
      within(savingsCard).getByText(/fatura deste ciclo não tem a tarifa com impostos registrada/)
    ).toBeInTheDocument()
  })

  it('com investimento cadastrado, "Retorno do investimento" vem DEPOIS da conta do ciclo e sem formulário de cadastro', () => {
    render(
      <FinancialSection
        indicators={buildIndicators({ bill_without_solar_brl: 540.11, compensated_kwh: 90 })}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn({
          data: {
            plant_id: 'plant-1',
            investment_amount_brl: '11200.00',
            investment_recorded_on: '2025-09-01',
            commissioned_on: '2025-09-01',
            accumulated_savings_brl: '264.00',
            average_monthly_savings_brl: '264.00',
            cycles_counted: 1,
            cycles_expected: 1,
            roi_percent: '2.36',
            payback_projection_months: 42,
            unavailable_reason: null,
            payback_unavailable_reason: null,
          },
        })}
      />
    )

    const headings = screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent)
    expect(headings).toEqual(['Sua conta com e sem a usina', 'Retorno do investimento'])
    expect(screen.queryByLabelText(/valor investido/i)).not.toBeInTheDocument()
  })

  it('sem investimento cadastrado, não há formulário de investimento em Dinheiro (o cadastro é só em Minha usina)', () => {
    render(
      <FinancialSection indicators={buildIndicators()} referenceMonth="2026-07" financialReturn={buildFinancialReturn()} />
    )

    expect(screen.queryByRole('heading', { level: 2, name: 'Retorno do investimento' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/valor investido/i)).not.toBeInTheDocument()
  })

  it('mostra RetryableError (não o card de retorno do investimento) quando financialReturn.error está presente, e refaz o fetch ao clicar em "Tentar novamente"', () => {
    const refetch = vi.fn()
    render(
      <FinancialSection
        indicators={buildIndicators()}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn({
          data: null,
          status: 'error',
          error: 'Erro ao buscar retorno do investimento.',
          refetch,
        })}
      />
    )

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Erro ao buscar retorno do investimento.')
    expect(screen.queryByLabelText(/valor investido/i)).not.toBeInTheDocument()

    screen.getByRole('button', { name: 'Tentar novamente' }).click()
    expect(refetch).toHaveBeenCalledTimes(1)
  })
})
