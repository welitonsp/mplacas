import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AppHeader } from './AppHeader'
import { useAuth } from '../contexts/AuthContext'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

const mockedUseAuth = vi.mocked(useAuth)

function setAuth(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  mockedUseAuth.mockReturnValue({
    isAuthenticated: true,
    username: 'maria',
    login: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  })
}

describe('AppHeader — menu de usuário', () => {
  it('abre o menu ao clicar no botão e mostra a ação "Sair"', () => {
    setAuth()
    render(<AppHeader />)

    const trigger = screen.getByRole('button', { name: /maria/i })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu')

    fireEvent.click(trigger)

    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('menuitem', { name: 'Sair' })).toBeInTheDocument()
    expect(trigger).toHaveAttribute('aria-controls', screen.getByRole('menu').id)
  })

  it('abre o menu via teclado (Enter/Space) e fecha com Escape', () => {
    setAuth()
    render(<AppHeader />)

    const trigger = screen.getByRole('button', { name: /maria/i })
    trigger.focus()

    fireEvent.keyDown(trigger, { key: 'Enter' })
    fireEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('fecha o menu ao clicar fora', () => {
    setAuth()
    render(
      <div>
        <AppHeader />
        <button type="button">fora</button>
      </div>
    )

    const trigger = screen.getByRole('button', { name: /maria/i })
    fireEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')

    fireEvent.mouseDown(screen.getByRole('button', { name: 'fora' }))
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('o botão "Sair" chama logout() do AuthContext', () => {
    const logout = vi.fn()
    setAuth({ logout })
    render(<AppHeader />)

    fireEvent.click(screen.getByRole('button', { name: /maria/i }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Sair' }))

    expect(logout).toHaveBeenCalledTimes(1)
  })

  it('o botão "Sair" tem estado de foco visível (focus-visible:ring)', () => {
    setAuth()
    render(<AppHeader />)

    fireEvent.click(screen.getByRole('button', { name: /maria/i }))

    expect(screen.getByRole('menuitem', { name: 'Sair' }).className).toMatch(/focus-visible:ring/)
  })
})

describe('AppHeader — slot de plantName (reservado para ADR-069)', () => {
  it('não renderiza nenhum texto de placeholder quando plantName está ausente', () => {
    setAuth()
    render(<AppHeader />)

    expect(screen.queryByText(/usina/i)).not.toBeInTheDocument()
  })

  it('renderiza o nome da usina quando plantName é passado', () => {
    setAuth()
    render(<AppHeader plantName="Usina Solar Norte" />)

    expect(screen.getByText('Usina Solar Norte')).toBeInTheDocument()
  })
})
