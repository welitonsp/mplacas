import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AppHeader } from './AppHeader'
import { useAuth } from '../contexts/AuthContext'
import { usePlant } from '../contexts/PlantContext'
import type { Plant } from '../lib/dashboard/plant-contracts'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../contexts/PlantContext', () => ({
  usePlant: vi.fn(),
}))

const mockedUseAuth = vi.mocked(useAuth)
const mockedUsePlant = vi.mocked(usePlant)

function setAuth(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  mockedUseAuth.mockReturnValue({
    isAuthenticated: true,
    username: 'maria',
    login: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  })
}

function setPlant(overrides: Partial<ReturnType<typeof usePlant>> = {}) {
  mockedUsePlant.mockReturnValue({
    plantId: null,
    plants: [],
    loading: false,
    error: null,
    selectPlant: vi.fn(),
    ...overrides,
  })
}

const PLANT_A: Plant = { id: 'p1', name: 'Usina Solar Norte', installedPowerKwp: '48.600' }
const PLANT_B: Plant = { id: 'p2', name: 'Filial Sul', installedPowerKwp: null }

describe('AppHeader — menu de usuário', () => {
  beforeEach(() => {
    setPlant()
  })

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

describe('AppHeader — seletor de usina (ADR-069, Etapa D)', () => {
  it('não renderiza nada relacionado a usina quando não há nenhuma no contexto', () => {
    setAuth()
    setPlant({ plants: [] })
    render(<AppHeader />)

    expect(screen.queryByText(/usina/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('renderiza o nome da usina como texto simples quando há exatamente uma', () => {
    setAuth()
    setPlant({ plantId: PLANT_A.id, plants: [PLANT_A] })
    render(<AppHeader />)

    expect(screen.getByText(PLANT_A.name)).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('renderiza um dropdown com as usinas quando há mais de uma', () => {
    setAuth()
    setPlant({ plantId: PLANT_A.id, plants: [PLANT_A, PLANT_B] })
    render(<AppHeader />)

    const select = screen.getByRole('combobox', { name: /usina ativa/i })
    expect(select).toBeInTheDocument()
    expect(screen.getByRole('option', { name: PLANT_A.name })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: PLANT_B.name })).toBeInTheDocument()
  })

  it('o restante do header (menu de usuário) continua intacto com o seletor presente', () => {
    setAuth()
    setPlant({ plantId: PLANT_A.id, plants: [PLANT_A, PLANT_B] })
    render(<AppHeader />)

    fireEvent.click(screen.getByRole('button', { name: /maria/i }))
    expect(screen.getByRole('menuitem', { name: 'Sair' })).toBeInTheDocument()
  })
})
