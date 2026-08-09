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
  it('agrupa os cards de dinheiro sob "Custo do ciclo" e os de energia sob "Créditos de energia" — tarifas/créditos compactados em tiras, sem perder nenhum card (ADR-072 Etapa 7; separação de grandeza, achado F3)', () => {
    const { container } = render(
      <FinancialSection
        indicators={buildIndicators()}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
        plantId="plant-1"
      />
    )

    // `FinancialSection` não tem mais heading "Financeiro" isolado (ADR-072,
    // Etapa 6 — o módulo que a hospeda já expõe esse texto como `<h1>` da
    // rota, ver `FinancialSection.tsx`) — a primeira `<section>` (das duas
    // que o componente devolve como irmãs) é a de "Custo do ciclo"/"Créditos
    // de energia".
    const section = container.querySelector('section') as HTMLElement

    // Ciclo de referência (achado F1) visível junto de "Custo do ciclo" —
    // único bloco cujo dado é estritamente do ciclo corrente.
    expect(within(section).getByText('Ciclo de referência: 2026-07')).toBeInTheDocument()

    const custoGrid = within(section).getByText('Valor total da fatura').closest('.grid')
    expect(custoGrid).not.toBeNull()
    expect(custoGrid!.children).toHaveLength(2)

    // Tarifas com/sem impostos: tira de 2 colunas dentro do bloco "Custo do
    // ciclo" (dinheiro) — nenhum dos 2 rótulos/valores some, só o invólucro
    // muda.
    const tarifaLabel = within(section).getByText('Tarifa com impostos')
    const tarifaStrip = tarifaLabel.closest('.grid') as HTMLElement
    expect(tarifaStrip).not.toBeNull()
    expect(tarifaStrip.children).toHaveLength(2)
    expect(within(tarifaStrip).getByText('Tarifa sem impostos')).toBeInTheDocument()
    // Saldo/cobertura de créditos não vivem mais na mesma tira que as
    // tarifas (achado F3: kWh não é a mesma grandeza de R$/kWh).
    expect(within(tarifaStrip).queryByText('Saldo de créditos')).not.toBeInTheDocument()
    expect(within(tarifaStrip).queryByText('Cobertura de créditos')).not.toBeInTheDocument()

    // Saldo/cobertura de créditos: tira própria de 2 colunas, fora do bloco
    // "Custo do ciclo".
    const creditoLabel = within(section).getByText('Saldo de créditos')
    const creditoStrip = creditoLabel.closest('.grid') as HTMLElement
    expect(creditoStrip).not.toBeNull()
    expect(creditoStrip.children).toHaveLength(2)
    expect(within(creditoStrip).getByText('Cobertura de créditos')).toBeInTheDocument()
    expect(creditoStrip).not.toBe(tarifaStrip)

    expect(within(section).getByText('Custo do ciclo')).toBeInTheDocument()
    // "Créditos de energia" volta a ser um heading próprio (h2, irmão de
    // "Custo do ciclo") — dado de energia não some sob um rótulo de dinheiro
    // (achado F3, já antecipado por
    // docs/UI_UX_AUDIT_2026-08-04.md P2-04 "Grandeza fora de lugar").
    expect(
      within(section).getByRole('heading', { level: 2, name: 'Créditos de energia' })
    ).toBeInTheDocument()
    expect(within(section).queryByText('Tarifas')).not.toBeInTheDocument()
  })

  it('renderiza todos os valores financeiros com a unidade correta quando a fatura tem tarifa registrada', () => {
    render(
      <FinancialSection
        indicators={buildIndicators()}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
        plantId="plant-1"
      />
    )

    expect(screen.getByText('Valor total da fatura')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*420,71/)).toBeInTheDocument()

    expect(screen.getByText('Iluminação pública')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*30,21/)).toBeInTheDocument()

    // Decomposição da fatura: `StackedBar` com energia + iluminação pública,
    // sem um terceiro segmento "Outros encargos" porque energia + iluminação
    // já reconstrói o total exatamente (mesma garantia do backend real — ver
    // `intelligence/energy_engine.py`).
    expect(screen.getByText('Componente energia')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*390,50/)).toBeInTheDocument()
    expect(screen.queryByText('Outros encargos')).not.toBeInTheDocument()

    const billBar = screen.getByRole('img', { name: /Total R\$\s*420,71/ })
    expect(billBar.getAttribute('aria-label')).toMatch(/Componente energia R\$\s*390,50/)
    expect(billBar.getAttribute('aria-label')).toMatch(/Iluminação pública R\$\s*30,21/)

    const tariffWithTaxesLabel = screen.getByText('Tarifa com impostos')
    const tariffWithTaxesCard = tariffWithTaxesLabel.closest('div') as HTMLElement
    expect(within(tariffWithTaxesCard).getByText(/0,85/)).toBeInTheDocument()
    expect(within(tariffWithTaxesCard).getByText('R$/kWh')).toBeInTheDocument()

    const tariffWithoutTaxesLabel = screen.getByText('Tarifa sem impostos')
    const tariffWithoutTaxesCard = tariffWithoutTaxesLabel.closest('div') as HTMLElement
    expect(within(tariffWithoutTaxesCard).getByText(/^0,6$/)).toBeInTheDocument()
    expect(within(tariffWithoutTaxesCard).getByText('R$/kWh')).toBeInTheDocument()

    expect(screen.getByText('Saldo de créditos')).toBeInTheDocument()
    expect(screen.getByText(/63,98/)).toBeInTheDocument()

    expect(screen.getByText('Cobertura de créditos')).toBeInTheDocument()

    expect(screen.getByText('Economia estimada')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*120,40/)).toBeInTheDocument()
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
        plantId="plant-1"
      />
    )

    const savingsLabel = screen.getByText('Economia estimada')
    const savingsCard = savingsLabel.closest('div') as HTMLElement

    expect(within(savingsCard).queryByText(/R\$\s*0,00/)).not.toBeInTheDocument()
    expect(
      within(savingsCard).getByText(/fatura deste ciclo não tem a tarifa com impostos registrada/)
    ).toBeInTheDocument()
  })

  it('renderiza "Retorno do investimento" como uma seção irmã de "Financeiro", com o formulário de cadastro de CAPEX quando o investimento ainda não foi registrado', () => {
    render(
      <FinancialSection
        indicators={buildIndicators()}
        referenceMonth="2026-07"
        financialReturn={buildFinancialReturn()}
        plantId="plant-1"
      />
    )

    // O texto "Retorno do investimento" aparece duas vezes de propósito: o
    // `<h2>` da seção (`SectionTitle`) e o rótulo do card dentro de
    // `FinancialReturnSection` — por isso a busca é restrita ao heading.
    expect(screen.getByRole('heading', { level: 2, name: 'Retorno do investimento' })).toBeInTheDocument()
    expect(
      screen.getByText(/cadastre o valor investido nesta usina para calcular o ROI/)
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/valor investido/i)).toBeInTheDocument()
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
        plantId="plant-1"
      />
    )

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Erro ao buscar retorno do investimento.')
    expect(screen.queryByLabelText(/valor investido/i)).not.toBeInTheDocument()

    screen.getByRole('button', { name: 'Tentar novamente' }).click()
    expect(refetch).toHaveBeenCalledTimes(1)
  })
})
