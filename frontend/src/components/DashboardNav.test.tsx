import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { DashboardNav } from './DashboardNav'
import {
  DASHBOARD_FINANCIAL_PATH,
  DASHBOARD_OVERVIEW_PATH,
  DASHBOARD_PRODUCTION_PATH,
  DASHBOARD_SETUP_PATH,
  DASHBOARD_TECHNICAL_PATH,
} from '../routes'

// Harness mínimo: as rotas reais das 4 abas + a subpágina técnica, para
// exercitar navegação de verdade. `NavLink`/`aria-current` só fazem sentido
// dentro de um roteador que resolve qual rota está ativa.
function renderNav(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <DashboardNav />
      <Routes>
        <Route path={DASHBOARD_OVERVIEW_PATH} element={<p>Conteúdo — Início</p>} />
        <Route path={DASHBOARD_PRODUCTION_PATH} element={<p>Conteúdo — Energia</p>} />
        <Route path={DASHBOARD_TECHNICAL_PATH} element={<p>Conteúdo — Detalhes técnicos</p>} />
        <Route path={DASHBOARD_FINANCIAL_PATH} element={<p>Conteúdo — Dinheiro</p>} />
        <Route path={DASHBOARD_SETUP_PATH} element={<p>Conteúdo — Minha usina</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

const TABS = ['Início', 'Energia', 'Dinheiro', 'Minha usina'] as const

describe('DashboardNav (ADR-083: 4 abas)', () => {
  it('renderiza um <nav aria-label="Seções do painel"> com as 4 abas, nesta ordem', () => {
    renderNav(DASHBOARD_OVERVIEW_PATH)

    expect(screen.getByRole('navigation', { name: 'Seções do painel' })).toBeInTheDocument()
    expect(screen.getAllByRole('link').map((link) => link.getAttribute('aria-label'))).toEqual([...TABS])
    expect(screen.queryByRole('link', { name: 'Técnico' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Visão Geral' })).not.toBeInTheDocument()
  })

  it('marca aria-current="page" apenas na aba ativa, e navega ao clicar nas outras', () => {
    renderNav(DASHBOARD_OVERVIEW_PATH)

    expect(screen.getByRole('link', { name: 'Início' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Conteúdo — Início')).toBeInTheDocument()

    for (const [name, content] of [
      ['Energia', 'Conteúdo — Energia'],
      ['Dinheiro', 'Conteúdo — Dinheiro'],
      ['Minha usina', 'Conteúdo — Minha usina'],
    ] as const) {
      fireEvent.click(screen.getByRole('link', { name }))
      expect(screen.getByRole('link', { name })).toHaveAttribute('aria-current', 'page')
      expect(screen.getByText(content)).toBeInTheDocument()
      for (const other of TABS.filter((tab) => tab !== name)) {
        expect(screen.getByRole('link', { name: other })).not.toHaveAttribute('aria-current')
      }
    }
  })

  it('"Energia" continua ativa nos detalhes técnicos, que moram dentro dela', () => {
    renderNav(DASHBOARD_TECHNICAL_PATH)

    expect(screen.getByText('Conteúdo — Detalhes técnicos')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Energia' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Início' })).not.toHaveAttribute('aria-current')
  })

  it('cada link usa o padrão de foco visível e touch target confortável', () => {
    renderNav(DASHBOARD_OVERVIEW_PATH)

    for (const name of TABS) {
      const link = screen.getByRole('link', { name })
      expect(link.className).toMatch(/focus-visible:ring-2 focus-visible:ring-\[var\(--color-brand-primary\)\]/)
      expect(link.className).toMatch(/min-h-\[56px\]/)
      expect(link.className).toMatch(/lg:min-h-\[44px\]/)
    }
  })

  it('não repete o antigo roteiro de leitura em toda tela', () => {
    renderNav(DASHBOARD_TECHNICAL_PATH)

    expect(screen.queryByText('Pergunta-chave')).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Rotina executiva de leitura' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link')).toHaveLength(4)
  })
})
