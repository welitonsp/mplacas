import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { InvestorPanelSection } from './InvestorPanelSection'
import { parseInvestorPanel } from '../lib/dashboard/investor-contracts'
import { investorAvailablePayload } from '../test/investorFixtures'
import { investorUnavailablePayload } from '../test/dashboardFixtures'

function renderSection(payload: unknown) {
  return render(
    <MemoryRouter>
      <InvestorPanelSection panel={parseInvestorPanel(payload)} error={null} onRetry={vi.fn()} />
    </MemoryRouter>,
  )
}

describe('InvestorPanelSection', () => {
  it('mostra TIR contra CDI líquido, VPL, payback e o veredito', () => {
    renderSection(investorAvailablePayload)
    expect(screen.getByRole('heading', { name: /Usina × CDI/ })).toBeInTheDocument()
    expect(screen.getByText('32,9% a.a.')).toBeInTheDocument()
    expect(screen.getByText('13,3% a.a.')).toBeInTheDocument()
    expect(screen.getByText('3 anos e 8 meses')).toBeInTheDocument()
    expect(screen.getByText(/19,6 pontos acima do CDI líquido de IR/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Patrimônio em 25 anos/ })).toBeInTheDocument()
  })

  it('com poucas faturas, não compara o realizado: mostra o que falta', () => {
    renderSection(investorAvailablePayload)
    expect(screen.getByText(/Faltam faturas de 11 meses desde a ligação/)).toBeInTheDocument()
    expect(screen.queryByText('Investimento só no CDI')).not.toBeInTheDocument()
  })

  it('com cobertura completa, compara os dois caminhos líquidos de IR', () => {
    renderSection({
      ...investorAvailablePayload,
      realized: { ...investorAvailablePayload.realized, cycles_counted: 12 },
    })
    expect(screen.getByText('Investimento só no CDI')).toBeInTheDocument()
    expect(screen.getByText('Economias aplicadas no CDI')).toBeInTheDocument()
  })

  it('premissas ficam visíveis, incluindo o Fio B e a base de poucas faturas', () => {
    renderSection(investorAvailablePayload)
    expect(screen.getByText('Premissas da projeção')).toBeInTheDocument()
    expect(screen.getByText(/75% em 2027, 90% em 2028/)).toBeInTheDocument()
    expect(screen.getByText(/a lei usa a data do pedido de conexão/)).toBeInTheDocument()
    expect(screen.getByText(/IR regressivo sobre o ganho/)).toBeInTheDocument()
  })

  it('com poucas faturas, avisa ACIMA dos números que a projeção é preliminar', () => {
    renderSection(investorAvailablePayload)
    const note = screen.getByRole('note', { name: 'Avisos sobre a projeção' })
    expect(note).toHaveTextContent('Estimativa preliminar')
    expect(note).toHaveTextContent(/1 fatura confirmada: ainda não cobre as estações do ano/)
    // O aviso vem antes dos indicadores na ordem de leitura.
    const tir = screen.getByText('Rendimento da usina (TIR)')
    expect(note.compareDocumentPosition(tir) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('sinaliza faturas calculadas antes da correção 0.3.0', () => {
    renderSection({ ...investorAvailablePayload, includes_pre_correction_cycles: true })
    expect(screen.getByRole('note', { name: 'Avisos sobre a projeção' })).toHaveTextContent(/antes da correção/)
  })

  it('com 12 faturas e versão corrigida, não mostra aviso', () => {
    renderSection({ ...investorAvailablePayload, low_confidence_baseline: false, includes_pre_correction_cycles: false })
    expect(screen.queryByRole('note', { name: 'Avisos sobre a projeção' })).toBeNull()
  })

  it('sem investimento cadastrado, leva para Minha usina', () => {
    renderSection(investorUnavailablePayload)
    expect(screen.getByText('Informe o valor investido')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ir para Minha usina' })).toHaveAttribute('href', '/dashboard/minha-usina')
  })
})
