import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { DashboardNav } from './DashboardNav'
import {
  DASHBOARD_FINANCIAL_PATH,
  DASHBOARD_OVERVIEW_PATH,
  DASHBOARD_PRODUCTION_PATH,
  DASHBOARD_TECHNICAL_PATH,
} from '../routes'

// Harness mínimo: 4 rotas reais (não só o `DashboardNav` isolado), para
// exercitar navegação de verdade — `NavLink`/`aria-current` só fazem sentido
// dentro de um roteador que resolve qual rota está ativa.
function renderNav(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <DashboardNav />
      <Routes>
        <Route path={DASHBOARD_OVERVIEW_PATH} element={<p>Conteúdo — Visão Geral</p>} />
        <Route path={DASHBOARD_PRODUCTION_PATH} element={<p>Conteúdo — Produção</p>} />
        <Route path={DASHBOARD_FINANCIAL_PATH} element={<p>Conteúdo — Financeiro</p>} />
        <Route path={DASHBOARD_TECHNICAL_PATH} element={<p>Conteúdo — Técnico</p>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('DashboardNav', () => {
  it('renderiza um <nav aria-label="Seções do painel"> com os 4 links', () => {
    renderNav(DASHBOARD_OVERVIEW_PATH)

    const nav = screen.getByRole('navigation', { name: 'Seções do painel' })
    expect(nav).toBeInTheDocument()

    expect(screen.getByRole('link', { name: 'Visão Geral' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Produção' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Financeiro' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Técnico' })).toBeInTheDocument()
  })

  it('marca aria-current="page" apenas no link do módulo ativo, e navega ao clicar nos outros 3', () => {
    renderNav(DASHBOARD_OVERVIEW_PATH)

    expect(screen.getByRole('link', { name: 'Visão Geral' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Produção' })).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('link', { name: 'Financeiro' })).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('link', { name: 'Técnico' })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('Conteúdo — Visão Geral')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Produção' }))
    expect(screen.getByRole('link', { name: 'Produção' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Visão Geral' })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('Conteúdo — Produção')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Financeiro' }))
    expect(screen.getByRole('link', { name: 'Financeiro' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Produção' })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('Conteúdo — Financeiro')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Técnico' }))
    expect(screen.getByRole('link', { name: 'Técnico' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Financeiro' })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('Conteúdo — Técnico')).toBeInTheDocument()
  })

  it('cada link usa o padrão de foco visível e touch target confortável', () => {
    renderNav(DASHBOARD_OVERVIEW_PATH)

    for (const name of ['Visão Geral', 'Produção', 'Financeiro', 'Técnico']) {
      const link = screen.getByRole('link', { name })
      expect(link.className).toMatch(/focus-visible:ring-2 focus-visible:ring-\[var\(--color-brand-primary\)\]/)
      expect(link.className).toMatch(/min-h-\[56px\]/)
    }
  })
})
