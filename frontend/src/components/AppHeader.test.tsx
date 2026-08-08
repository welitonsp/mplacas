import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AppHeader } from './AppHeader'
import { useAuth } from '../contexts/AuthContext'
import { usePlant } from '../contexts/PlantContext'
import type { Plant } from '../lib/dashboard/plant-contracts'
import * as theme from '../lib/theme'

const THEME_STORAGE_KEY = 'mplacas:theme'

/**
 * jsdom não implementa `matchMedia` de verdade (`src/test/setup.ts` só
 * cobre o mínimo pra não lançar). Mesmo stub de `theme.test.ts`, com
 * `fireChange` para simular o evento `change` que `watchSystemTheme`
 * escuta — usado pelos testes de "Sistema" reagindo ao SO em tempo real.
 */
function stubMatchMedia(matchesDark: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>()

  const mql = {
    matches: matchesDark,
    media: '(prefers-color-scheme: dark)',
    addEventListener: vi.fn((event: string, listener: (event: MediaQueryListEvent) => void) => {
      if (event === 'change') listeners.add(listener)
    }),
    removeEventListener: vi.fn((event: string, listener: (event: MediaQueryListEvent) => void) => {
      if (event === 'change') listeners.delete(listener)
    }),
  }

  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => mql)
  )

  return {
    fireChange(matches: boolean) {
      mql.matches = matches
      for (const listener of listeners) {
        listener({ matches } as MediaQueryListEvent)
      }
    },
  }
}

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

describe('AppHeader — controle de aparência (ADR-071, Fase 3)', () => {
  beforeEach(() => {
    setAuth()
    setPlant()
    window.localStorage.clear()
    delete document.documentElement.dataset.theme
  })

  afterEach(() => {
    window.localStorage.clear()
    delete document.documentElement.dataset.theme
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function openMenu() {
    render(<AppHeader />)
    fireEvent.click(screen.getByRole('button', { name: /maria/i }))
  }

  it('mostra as três opções com nome acessível em texto visível', () => {
    stubMatchMedia(false)
    openMenu()

    expect(screen.getByRole('menuitemradio', { name: 'Sistema' })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: 'Claro' })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: 'Escuro' })).toBeInTheDocument()
  })

  it('"Sistema" é a opção marcada por padrão, via aria-checked (nenhuma chave salva)', () => {
    stubMatchMedia(false)
    openMenu()

    expect(screen.getByRole('menuitemradio', { name: 'Sistema' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('menuitemradio', { name: 'Claro' })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('menuitemradio', { name: 'Escuro' })).toHaveAttribute('aria-checked', 'false')
  })

  it('clicar em "Claro" chama setThemePreference("light") e reflete em document.documentElement.dataset.theme', () => {
    stubMatchMedia(true) // SO prefere escuro — a escolha manual precisa vencer
    const setThemePreferenceSpy = vi.spyOn(theme, 'setThemePreference')
    openMenu()

    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Claro' }))

    expect(setThemePreferenceSpy).toHaveBeenCalledWith('light')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(screen.getByRole('menuitemradio', { name: 'Claro' })).toHaveAttribute('aria-checked', 'true')
  })

  it('clicar em "Escuro" chama setThemePreference("dark") e reflete em document.documentElement.dataset.theme', () => {
    stubMatchMedia(false)
    const setThemePreferenceSpy = vi.spyOn(theme, 'setThemePreference')
    openMenu()

    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Escuro' }))

    expect(setThemePreferenceSpy).toHaveBeenCalledWith('dark')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(screen.getByRole('menuitemradio', { name: 'Escuro' })).toHaveAttribute('aria-checked', 'true')
  })

  it('clicar em "Sistema" chama setThemePreference("system"), remove a chave e aplica o tema resolvido do SO', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    stubMatchMedia(false) // SO prefere claro
    const setThemePreferenceSpy = vi.spyOn(theme, 'setThemePreference')
    openMenu()

    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Sistema' }))

    expect(setThemePreferenceSpy).toHaveBeenCalledWith('system')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('é navegável só por teclado: a opção recebe foco (Tab) e Enter/Space seleciona', () => {
    stubMatchMedia(false)
    const setThemePreferenceSpy = vi.spyOn(theme, 'setThemePreference')
    openMenu()

    const darkOption = screen.getByRole('menuitemradio', { name: 'Escuro' })
    darkOption.focus()
    expect(darkOption).toHaveFocus()

    fireEvent.keyDown(darkOption, { key: 'Enter' })
    fireEvent.click(darkOption)

    expect(setThemePreferenceSpy).toHaveBeenCalledWith('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('as três opções têm foco visível (focus-visible:ring), mesmo padrão do resto do header', () => {
    stubMatchMedia(false)
    openMenu()

    for (const label of ['Sistema', 'Claro', 'Escuro']) {
      expect(screen.getByRole('menuitemradio', { name: label }).className).toMatch(/focus-visible:ring/)
    }
  })

  it('reage a uma mudança simulada de matchMedia enquanto "Sistema" está ativo', () => {
    const media = stubMatchMedia(false)
    const applyThemeSpy = vi.spyOn(theme, 'applyTheme')
    openMenu()

    media.fireChange(true)

    expect(applyThemeSpy).toHaveBeenCalledWith('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('não reage mais à mudança do SO depois que o usuário escolheu "Claro"/"Escuro" manualmente', () => {
    const media = stubMatchMedia(false)
    openMenu()

    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Claro' }))

    const applyThemeSpy = vi.spyOn(theme, 'applyTheme')
    media.fireChange(true)

    expect(applyThemeSpy).not.toHaveBeenCalled()
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
