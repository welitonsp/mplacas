import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
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
    expect(screen.getByText('Projeção: retorno anual (TIR)')).toBeInTheDocument()
    expect(screen.getByText('32,9% a.a.')).toBeInTheDocument()
    expect(screen.getByText('13,3% a.a.')).toBeInTheDocument()
    expect(screen.getByText('3 anos e 8 meses')).toBeInTheDocument()
    expect(screen.getByText(/19,6 pontos acima do CDI líquido de IR/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Patrimônio em 25 anos, em dinheiro de hoje/ })).toBeInTheDocument()
    // VPL: a base de comparação é dita, não "em dinheiro de hoje".
    expect(screen.getAllByText(/a mais que o CDI, trazido a valor presente pelo próprio CDI/).length).toBeGreaterThan(0)
    expect(screen.queryByText('Em dinheiro de hoje')).not.toBeInTheDocument()
  })

  it('o selo de projeção aparece sempre, mesmo sem aviso de poucas faturas', () => {
    renderSection({ ...investorAvailablePayload, low_confidence_baseline: false, includes_pre_correction_cycles: false })
    expect(screen.queryByRole('note', { name: 'Avisos sobre a projeção' })).toBeNull()
    const group = screen.getByRole('group', { name: 'Projeção' })
    expect(within(group).getByText('Projeção')).toBeInTheDocument()
    expect(within(group).getByText(/não é resultado já obtido/)).toBeInTheDocument()
    expect(within(group).getByText('Projeção: retorno anual (TIR)')).toBeInTheDocument()
  })

  it('diz quanto do investimento a usina devolve por ano, como REALIZADO e fora do grupo Projeção', () => {
    renderSection(investorAvailablePayload)
    // 0,2829 vindo do backend → 28%.
    const line = screen.getByText(/A usina devolve cerca de 28% do investimento por ano/)
    expect(screen.getByRole('group', { name: 'Projeção' })).not.toContainElement(line)
    expect(screen.getByText('Realizado', { exact: true })).toBeInTheDocument()
    // Com 1 mês de faturas é média anualizada, e o texto diz "último mês".
    expect(screen.getByText(/Média anualizada: economia do último mês de faturas confirmadas/)).toBeInTheDocument()
    expect(screen.queryByText(/últimos 1 mês/)).not.toBeInTheDocument()
  })

  it('com 12 meses de faturas, não fala em média anualizada', () => {
    renderSection({
      ...investorAvailablePayload,
      projection: { ...investorAvailablePayload.projection, baseline_cycles: 12 },
    })
    expect(screen.getByText(/Economia dos últimos 12 meses de faturas confirmadas/)).toBeInTheDocument()
    expect(screen.queryByText(/Média anualizada/)).not.toBeInTheDocument()
  })

  it('rotula a diferença entre os dois paybacks da aba', () => {
    renderSection(investorAvailablePayload)
    expect(screen.getByText(/Projeção com manutenção e inversor\. Contando o CDI/)).toBeInTheDocument()
  })

  it('VPL: rótulo neutro, valor absoluto e "a mais/a menos"', () => {
    renderSection({
      ...investorAvailablePayload,
      projection: { ...investorAvailablePayload.projection, npv_at_cdi_net_brl: '-4200.50' },
    })
    expect(screen.getByText('Diferença para o CDI (VPL)')).toBeInTheDocument()
    expect(screen.getByText('R$ 4.200,50')).toBeInTheDocument()
    expect(screen.getAllByText(/a menos que o CDI, trazido a valor presente pelo próprio CDI/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/-4\.200/)).not.toBeInTheDocument()
  })

  it('mostra o patrimônio em dinheiro de hoje, com a inflação e o CDI usados, e a premissa visível', () => {
    renderSection(investorAvailablePayload)
    expect(screen.getByText(/Em dinheiro de hoje \(corrigido pela inflação de 4,6% a\.a\.\)/)).toBeInTheDocument()
    expect(screen.getByText('Supõe aplicar toda a economia no CDI de 14% a.a. por 25 anos.')).toBeInTheDocument()
  })

  it('resume as premissas à vista, sem abrir o bloco recolhido', () => {
    renderSection(investorAvailablePayload)
    const summary = screen.getByText(/^Premissas: CDI 14% a\.a\./)
    expect(summary).toHaveTextContent('inflação 4,6% a.a.')
    expect(summary).toHaveTextContent('placas perdem 0,5% a.a.')
    expect(summary).toHaveTextContent('Fio B subindo até 100% em 2029')
    expect(summary).toHaveTextContent('inversor trocado nos anos 12 e 24 (35% do investimento)')
    expect(summary).toHaveTextContent('manutenção 1% do investimento ao ano')
  })

  it('sem a série em dinheiro de hoje, esconde o gráfico em vez de usar zero ou o nominal', () => {
    renderSection({
      ...investorAvailablePayload,
      projection: {
        ...investorAvailablePayload.projection,
        patrimony: investorAvailablePayload.projection.patrimony.map((point) => ({
          year: point.year,
          cdi_path_brl: point.cdi_path_brl,
          solar_path_brl: point.solar_path_brl,
        })),
      },
    })
    expect(screen.queryByRole('img', { name: /Patrimônio em/ })).not.toBeInTheDocument()
    expect(screen.getByText(/evolução do patrimônio em dinheiro de hoje não está disponível/)).toBeInTheDocument()
  })

  it('sem o campo da diferença TIR − CDI, o veredito não inventa pontos', () => {
    renderSection({
      ...investorAvailablePayload,
      projection: { ...investorAvailablePayload.projection, irr_spread_over_cdi_per_year: null },
    })
    expect(screen.queryByText(/pontos acima/)).not.toBeInTheDocument()
    expect(screen.queryByText(/pontos abaixo/)).not.toBeInTheDocument()
    expect(screen.getByText(/Projeção: a usina rende 32,9% ao ano\./)).toBeInTheDocument()
  })

  it('sem VPL, não escreve "R$ 0,00 a mais/menos"', () => {
    renderSection({
      ...investorAvailablePayload,
      projection: { ...investorAvailablePayload.projection, npv_at_cdi_net_brl: 'nao-numero' },
    })
    expect(screen.queryByText(/Vale R\$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/R\$\s*0,00/)).not.toBeInTheDocument()
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
    expect(screen.getByText(/último mês com CDI publicado/)).toBeInTheDocument()
  })

  it('premissas ficam visíveis, incluindo o Fio B e a base de poucas faturas', () => {
    renderSection(investorAvailablePayload)
    expect(screen.getByText('Premissas da projeção')).toBeInTheDocument()
    expect(screen.getByText(/75% em 2027, 90% em 2028/)).toBeInTheDocument()
    expect(screen.getByText(/a lei usa a data do pedido de conexão/)).toBeInTheDocument()
    expect(screen.getByText(/IR regressivo sobre o ganho/)).toBeInTheDocument()
    expect(screen.getByText(/Premissas de custo conservadoras: manutenção de 1%/)).toBeInTheDocument()
    expect(screen.getByText(/troca do inversor nos anos 12 e 24, cada uma a 35% do investimento em dinheiro de hoje/)).toBeInTheDocument()
    expect(screen.getByText(/Em valores nominais \(sem descontar a inflação\), em 25 anos/)).toBeInTheDocument()
  })

  it('com poucas faturas, avisa ACIMA dos números que a projeção é preliminar', () => {
    renderSection(investorAvailablePayload)
    const note = screen.getByRole('note', { name: 'Avisos sobre a projeção' })
    expect(note).toHaveTextContent('Estimativa preliminar')
    expect(note).toHaveTextContent(/1 fatura confirmada: ainda não cobre as estações do ano/)
    // O aviso vem antes dos indicadores na ordem de leitura.
    const tir = screen.getByText('Projeção: retorno anual (TIR)')
    expect(note.compareDocumentPosition(tir) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('versão antiga do cálculo: avisa que tende a SUBESTIMAR (e não que superestima)', () => {
    renderSection({ ...investorAvailablePayload, includes_pre_correction_cycles: true, pre_injection_fix: true })
    const note = screen.getByRole('note', { name: 'Avisos sobre a projeção' })
    expect(note).toHaveTextContent(/tende a subestimar a economia/)
    expect(note).not.toHaveTextContent(/superestimar/)
    expect(note).not.toHaveTextContent(/valor mínimo \(piso\)/)
  })

  it('ciclo sem tarifa homologada: avisa que é um piso, com frase própria', () => {
    renderSection({ ...investorAvailablePayload, includes_pre_correction_cycles: true, bill_tariff_floor: true })
    const note = screen.getByRole('note', { name: 'Avisos sobre a projeção' })
    expect(note).toHaveTextContent(/valor mínimo \(piso\)/)
    expect(note).not.toHaveTextContent(/versão anterior do cálculo/)
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

  it('sem faturas confirmadas, diz que a importação fica no fim da aba e o botão leva até ela', () => {
    renderSection({ ...investorUnavailablePayload, unavailable_reason: 'NO_CONSOLIDATED_SAVINGS' })
    expect(screen.getByText(/na seção Faturas de energia, no fim desta página/)).toBeInTheDocument()
    expect(screen.queryByText(/no topo desta página/)).not.toBeInTheDocument()

    const target = document.createElement('div')
    target.id = 'faturas'
    const scroll = vi.fn()
    target.scrollIntoView = scroll
    const importButton = document.createElement('button')
    importButton.id = 'bill-import-button'
    document.body.append(target, importButton)
    fireEvent.click(screen.getByRole('button', { name: 'Ir para as faturas' }))
    expect(scroll).toHaveBeenCalledWith({ block: 'start' })
    expect(importButton).toHaveFocus()
    target.remove()
    importButton.remove()
  })
})
