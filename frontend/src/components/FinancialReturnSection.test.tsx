import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { FinancialReturnResponse } from '../lib/dashboard/financial-return-contracts'
import { FinancialReturnSection } from './FinancialReturnSection'

function buildAvailable(overrides: Partial<FinancialReturnResponse> = {}): FinancialReturnResponse {
  return {
    plant_id: '11111111-1111-1111-1111-111111111111',
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

describe('FinancialReturnSection', () => {
  it('renderiza a barra de progresso com role="progressbar" e o percentual textual quando os dados estão disponíveis', () => {
    render(
      <FinancialReturnSection
        financialReturn={buildAvailable()}
        plantId="plant-1"
        onInvestmentRegistered={() => {}}
      />
    )

    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '19')
    expect(bar).toHaveAttribute('aria-valuemin', '0')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(screen.getByText('19')).toBeInTheDocument()
  })

  it('renderiza a mensagem de cobertura parcial quando cycles_counted < cycles_expected', () => {
    render(
      <FinancialReturnSection
        financialReturn={buildAvailable({ cycles_counted: 12, cycles_expected: 17 })}
        plantId="plant-1"
        onInvestmentRegistered={() => {}}
      />
    )

    expect(
      screen.getByText('Baseado em 12 de 17 ciclos com relatório consolidado.')
    ).toBeInTheDocument()
  })

  it('não renderiza rótulo de cobertura quando os ciclos coincidem', () => {
    render(
      <FinancialReturnSection
        financialReturn={buildAvailable({ cycles_counted: 17, cycles_expected: 17 })}
        plantId="plant-1"
        onInvestmentRegistered={() => {}}
      />
    )

    expect(screen.queryByText(/ciclos com relatório consolidado/)).not.toBeInTheDocument()
  })

  it('renderiza "investimento já recuperado" quando o payback já foi atingido', () => {
    render(
      <FinancialReturnSection
        financialReturn={buildAvailable({ cycles_counted: 20, payback_projection_months: 20 })}
        plantId="plant-1"
        onInvestmentRegistered={() => {}}
      />
    )

    expect(screen.getByText('Investimento já recuperado.')).toBeInTheDocument()
    expect(screen.queryByText(/Projeção de payback/)).not.toBeInTheDocument()
  })

  it('rotula a projeção de payback como projeção, com a premissa visível', () => {
    render(
      <FinancialReturnSection
        financialReturn={buildAvailable()}
        plantId="plant-1"
        onInvestmentRegistered={() => {}}
      />
    )

    expect(screen.getByText(/Projeção de payback:/)).toBeInTheDocument()
    expect(screen.getByText(/64/)).toBeInTheDocument()
    expect(screen.getByText(/mantida a média de economia dos últimos ciclos/)).toBeInTheDocument()
  })

  it('renderiza mensagem específica para INVESTMENT_NOT_REGISTERED e o formulário de cadastro', () => {
    render(
      <FinancialReturnSection
        financialReturn={buildAvailable({
          investment_amount_brl: null,
          investment_recorded_on: null,
          accumulated_savings_brl: null,
          average_monthly_savings_brl: null,
          cycles_counted: null,
          cycles_expected: null,
          roi_percent: null,
          payback_projection_months: null,
          unavailable_reason: 'INVESTMENT_NOT_REGISTERED',
        })}
        plantId="plant-1"
        onInvestmentRegistered={() => {}}
      />
    )

    expect(screen.getByText(/cadastre o valor investido/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cadastrar investimento/i })).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByText('R$ 0,00')).not.toBeInTheDocument()
    expect(screen.queryByText(/^0%$/)).not.toBeInTheDocument()
  })

  it('renderiza mensagem específica para NO_CONSOLIDATED_SAVINGS, sem formulário e sem R$ 0,00/0% fabricados', () => {
    render(
      <FinancialReturnSection
        financialReturn={buildAvailable({
          accumulated_savings_brl: null,
          average_monthly_savings_brl: null,
          cycles_counted: 0,
          roi_percent: null,
          payback_projection_months: null,
          unavailable_reason: 'NO_CONSOLIDATED_SAVINGS',
        })}
        plantId="plant-1"
        onInvestmentRegistered={() => {}}
      />
    )

    expect(screen.getByText(/nenhum ciclo com relatório consolidado tem economia calculada/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cadastrar investimento/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByText('R$ 0,00')).not.toBeInTheDocument()
  })

  it('renderiza mensagem específica de payback para INSUFFICIENT_HISTORY mantendo o ROI visível', () => {
    render(
      <FinancialReturnSection
        financialReturn={buildAvailable({
          cycles_counted: 3,
          payback_projection_months: null,
          payback_unavailable_reason: 'INSUFFICIENT_HISTORY',
        })}
        plantId="plant-1"
        onInvestmentRegistered={() => {}}
      />
    )

    // ROI continua visível — o motivo de indisponibilidade é só do payback.
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
    expect(screen.getByText('19')).toBeInTheDocument()
    expect(screen.getByText(/6 ciclos com relatório consolidado/)).toBeInTheDocument()
    expect(screen.queryByText(/Projeção de payback:/)).not.toBeInTheDocument()
  })

  it('mostra um estado de carregamento (sem barra/percentual) quando financialReturn é null', () => {
    render(
      <FinancialReturnSection financialReturn={null} plantId="plant-1" onInvestmentRegistered={vi.fn()} />
    )
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
})
