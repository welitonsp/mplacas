import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ExecutiveIndicators } from '../lib/dashboard/contracts'
import type { FinancialReturnResponse } from '../lib/dashboard/financial-return-contracts'
import { FinancialDecisionPanel, buildFinancialDecision } from './FinancialDecisionPanel'

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

function buildReturn(overrides: Partial<FinancialReturnResponse> = {}): FinancialReturnResponse {
  return {
    plant_id: 'plant-1',
    investment_amount_brl: '48000.00',
    investment_recorded_on: '2024-03-11',
    commissioned_on: '2024-03-01',
    accumulated_savings_brl: '9120.55',
    average_monthly_savings_brl: '760.05',
    cycles_counted: 12,
    cycles_expected: 17,
    roi_percent: '19.0',
    payback_projection_months: 64,
    unavailable_reason: null,
    payback_unavailable_reason: null,
    ...overrides,
  }
}

describe('FinancialDecisionPanel', () => {
  it('usa estado operacional enquanto ROI e payback ainda carregam', () => {
    render(
      <FinancialDecisionPanel
        indicators={buildIndicators()}
        referenceMonth="2026-07"
        financialReturn={null}
        financialReturnError={null}
      />,
    )

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Decisão financeira')
    expect(screen.getByRole('heading', { level: 2, name: 'Calculando retorno financeiro' })).toBeInTheDocument()
    expect(status).toHaveTextContent('ROI e payback ainda estão sendo carregados.')
    expect(status).toHaveTextContent('Aguardar leitura')

    const plan = screen.getByRole('list', { name: 'Plano financeiro executivo' })
    expect(within(plan).getByText('Aguardar retorno')).toBeInTheDocument()
  })

  it('usa estado operacional quando o retorno financeiro falha', () => {
    render(
      <FinancialDecisionPanel
        indicators={buildIndicators()}
        referenceMonth="2026-07"
        financialReturn={null}
        financialReturnError="Erro ao buscar retorno do investimento."
      />,
    )

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Decisão financeira bloqueada')
    expect(status).toHaveTextContent('ROI e payback não devem ser usados para decisão.')
    expect(status).toHaveTextContent('Reprocessar hoje')
  })
  it('orienta cadastrar CAPEX quando o ROI está bloqueado por investimento pendente', () => {
    const financialReturn = buildReturn({
      investment_amount_brl: null,
      accumulated_savings_brl: null,
      average_monthly_savings_brl: null,
      cycles_counted: null,
      cycles_expected: null,
      roi_percent: null,
      payback_projection_months: null,
      unavailable_reason: 'INVESTMENT_NOT_REGISTERED',
      payback_unavailable_reason: 'INVESTMENT_NOT_REGISTERED',
    })

    render(
      <FinancialDecisionPanel
        indicators={buildIndicators()}
        referenceMonth="2026-07"
        financialReturn={financialReturn}
        financialReturnError={null}
      />,
    )

    expect(screen.getByRole('heading', { level: 2, name: 'ROI bloqueado por CAPEX pendente' })).toBeInTheDocument()
    expect(screen.getAllByText('Cadastrar investimento').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Gestão financeira')).toBeInTheDocument()
    expect(screen.getByText(/Cadastrar o CAPEX da usina/)).toBeInTheDocument()

    const plan = screen.getByRole('list', { name: 'Plano financeiro executivo' })
    expect(within(plan).getByText('Confirmar CAPEX')).toBeInTheDocument()
    expect(within(plan).getByText('Cadastrar investimento')).toBeInTheDocument()
    expect(within(plan).getByText('Recalcular decisão')).toBeInTheDocument()
  })

  it('mostra investimento recuperado quando o payback já foi atingido', () => {
    const decision = buildFinancialDecision({
      indicators: buildIndicators(),
      referenceMonth: '2026-07',
      financialReturn: buildReturn({
        accumulated_savings_brl: '52000.00',
        roi_percent: '108.3',
        cycles_counted: 20,
        payback_projection_months: 20,
      }),
      financialReturnError: null,
    })

    expect(decision.tone).toBe('success')
    expect(decision.title).toBe('Investimento recuperado')
    expect(decision.label).toBe('Payback atingido')
    expect(decision.playbook.map((step) => step.title)).toEqual([
      'Registrar marco',
      'Separar ganho futuro',
      'Comparar carteira',
    ])
  })

  it('mantém ROI visível e bloqueia só o payback quando falta histórico suficiente', () => {
    const decision = buildFinancialDecision({
      indicators: buildIndicators({ credit_coverage_rate_percent: 62 }),
      referenceMonth: '2026-07',
      financialReturn: buildReturn({
        cycles_counted: 3,
        payback_projection_months: null,
        payback_unavailable_reason: 'INSUFFICIENT_HISTORY',
      }),
      financialReturnError: null,
    })

    expect(decision.tone).toBe('warning')
    expect(decision.title).toBe('ROI disponível, payback ainda sem base')
    expect(decision.evidence.find((item) => item.label === 'ROI acumulado')?.value).toBe('19%')
    expect(decision.evidence.find((item) => item.label === 'Cobertura créditos')?.tone).toBe('danger')
    expect(decision.primaryAction).toMatch(/evitar conclusão de prazo/)
  })
})
