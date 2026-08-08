import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AppShell } from './AppShell'
import { useAuth } from '../contexts/AuthContext'
import { usePlant } from '../contexts/PlantContext'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../contexts/PlantContext', () => ({
  usePlant: vi.fn(),
}))

vi.mocked(useAuth).mockReturnValue({
  isAuthenticated: true,
  username: null,
  login: vi.fn(),
  logout: vi.fn(),
})

vi.mocked(usePlant).mockReturnValue({
  plantId: null,
  plants: [],
  loading: false,
  error: null,
  selectPlant: vi.fn(),
})

describe('AppShell — slot subnav (ADR-072, Etapa 1)', () => {
  it('sem subnav, não renderiza nada extra entre o header e o <main>', () => {
    const { container } = render(
      <AppShell>
        <p>conteúdo</p>
      </AppShell>
    )

    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    expect(container.querySelector('header + main')).not.toBeNull()
  })

  it('com subnav, renderiza entre o header e o <main> — não dentro do <main>', () => {
    render(
      <AppShell subnav={<nav aria-label="Seções do painel">sub-navegação</nav>}>
        <p>conteúdo</p>
      </AppShell>
    )

    const nav = screen.getByRole('navigation', { name: 'Seções do painel' })
    expect(nav).toBeInTheDocument()

    const main = screen.getByRole('main')
    expect(main).not.toContainElement(nav)

    const header = document.querySelector('header')
    expect(header).not.toBeNull()
    // Ordem no DOM: header, depois subnav, depois main.
    expect(header!.compareDocumentPosition(nav) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(nav.compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

describe('AppShell — skip link', () => {
  it('o primeiro elemento focável é o skip link, e seu href aponta para o id do <main>', () => {
    const { container } = render(
      <AppShell>
        <p>conteúdo</p>
      </AppShell>
    )

    const focusable = container.querySelectorAll<HTMLElement>(
      'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    expect(focusable.length).toBeGreaterThan(0)

    const firstFocusable = focusable[0]
    expect(firstFocusable.tagName).toBe('A')
    expect(firstFocusable).toHaveTextContent('Pular para o conteúdo')

    const main = container.querySelector('main')
    expect(main).not.toBeNull()
    expect(firstFocusable.getAttribute('href')).toBe(`#${main!.id}`)
  })
})
