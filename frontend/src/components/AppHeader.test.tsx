import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
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

  it('mostra identidade operacional no botão do usuário em telas maiores', () => {
    setAuth({ username: 'maria.operacao@mplacas.com' })
    render(<AppHeader />)

    const trigger = screen.getByRole('button', { name: /maria.operacao@mplacas.com/i })
    expect(trigger).toHaveTextContent('Operador')
    expect(trigger).toHaveTextContent('maria.operacao@mplacas.com')
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

describe('AppHeader — controle de tema (ícone único no header, ADR-071 Fase 4)', () => {
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

  /** O botão-ícone de tema é identificado pelo `aria-label` dinâmico, que
   * sempre começa com "Tema: ". Não fica escondido em nenhum menu — está
   * sempre visível no cabeçalho, ao lado do menu do usuário. */
  function getThemeButton() {
    return screen.getByRole('button', { name: /^Tema:/ })
  }

  it('está sempre visível no cabeçalho, sem precisar abrir o menu do usuário', () => {
    stubMatchMedia(false)
    render(<AppHeader />)

    expect(getThemeButton()).toBeInTheDocument()
    // O menu do avatar segue fechado — o controle de tema não depende dele.
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('a lista de texto "Aparência" não existe mais dentro do menu do avatar', () => {
    stubMatchMedia(false)
    render(<AppHeader />)

    fireEvent.click(screen.getByRole('button', { name: /maria/i }))

    expect(screen.queryByText('Aparência')).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitemradio')).not.toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Sair' })).toBeInTheDocument()
  })

  it('preferência padrão "Sistema" com SO claro: aria-label/title anunciam "Sistema (aplicando claro)" e o próximo clique vai para claro', () => {
    stubMatchMedia(false) // SO prefere claro
    render(<AppHeader />)

    const button = getThemeButton()
    const expected = 'Tema: Sistema (aplicando claro). Clique para mudar para claro.'
    expect(button).toHaveAttribute('aria-label', expected)
    expect(button).toHaveAttribute('title', expected)
  })

  it('clique 1: system → light — chama setThemePreference("light") e aplica no DOM', () => {
    stubMatchMedia(true) // SO prefere escuro — não deve importar após a escolha manual
    const setThemePreferenceSpy = vi.spyOn(theme, 'setThemePreference')
    render(<AppHeader />)

    fireEvent.click(getThemeButton())

    expect(setThemePreferenceSpy).toHaveBeenCalledWith('light')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(getThemeButton()).toHaveAttribute('aria-label', 'Tema: Claro. Clique para mudar para escuro.')
  })

  it('clique 2: light → dark — chama setThemePreference("dark") e aplica no DOM', () => {
    stubMatchMedia(false)
    const setThemePreferenceSpy = vi.spyOn(theme, 'setThemePreference')
    render(<AppHeader />)

    fireEvent.click(getThemeButton()) // system -> light
    fireEvent.click(getThemeButton()) // light -> dark

    expect(setThemePreferenceSpy).toHaveBeenNthCalledWith(2, 'dark')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(getThemeButton()).toHaveAttribute('aria-label', 'Tema: Escuro. Clique para mudar para sistema.')
  })

  it('clique 3: dark → system — chama setThemePreference("system"), remove a chave e volta ao tema resolvido do SO', () => {
    stubMatchMedia(false) // SO prefere claro
    const setThemePreferenceSpy = vi.spyOn(theme, 'setThemePreference')
    render(<AppHeader />)

    fireEvent.click(getThemeButton()) // system -> light
    fireEvent.click(getThemeButton()) // light -> dark
    fireEvent.click(getThemeButton()) // dark -> system

    expect(setThemePreferenceSpy).toHaveBeenNthCalledWith(3, 'system')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(getThemeButton()).toHaveAttribute(
      'aria-label',
      'Tema: Sistema (aplicando claro). Clique para mudar para claro.'
    )
  })

  it('o ciclo completo (4 cliques) volta ao ponto de partida: system → light → dark → system', () => {
    stubMatchMedia(false)
    const setThemePreferenceSpy = vi.spyOn(theme, 'setThemePreference')
    render(<AppHeader />)

    fireEvent.click(getThemeButton())
    fireEvent.click(getThemeButton())
    fireEvent.click(getThemeButton())
    fireEvent.click(getThemeButton())

    expect(setThemePreferenceSpy.mock.calls.map((call) => call[0])).toEqual(['light', 'dark', 'system', 'light'])
  })

  it('é navegável só por teclado: o botão recebe foco (Tab) e Enter/Space ativa (comportamento nativo de <button>)', () => {
    stubMatchMedia(false)
    const setThemePreferenceSpy = vi.spyOn(theme, 'setThemePreference')
    render(<AppHeader />)

    const button = getThemeButton()
    button.focus()
    expect(button).toHaveFocus()

    fireEvent.keyDown(button, { key: 'Enter' })
    fireEvent.click(button)

    expect(setThemePreferenceSpy).toHaveBeenCalledWith('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('tem foco visível (focus-visible:ring), mesmo padrão do resto do header', () => {
    stubMatchMedia(false)
    render(<AppHeader />)

    expect(getThemeButton().className).toMatch(/focus-visible:ring/)
  })

  it('tem touch target mínimo de 44x44px', () => {
    stubMatchMedia(false)
    render(<AppHeader />)

    expect(getThemeButton().className).toMatch(/min-w-\[44px\]/)
    expect(getThemeButton().className).toMatch(/min-h-\[44px\]/)
  })

  it('enquanto a preferência é "Sistema", uma mudança simulada de matchMedia atualiza o ícone exibido (aria-label muda)', () => {
    const media = stubMatchMedia(false) // SO começa claro
    const applyThemeSpy = vi.spyOn(theme, 'applyTheme')
    render(<AppHeader />)

    expect(getThemeButton()).toHaveAttribute(
      'aria-label',
      'Tema: Sistema (aplicando claro). Clique para mudar para claro.'
    )

    act(() => {
      media.fireChange(true) // SO muda para escuro
    })

    expect(applyThemeSpy).toHaveBeenCalledWith('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(getThemeButton()).toHaveAttribute(
      'aria-label',
      'Tema: Sistema (aplicando escuro). Clique para mudar para claro.'
    )
  })

  it('não reage mais à mudança do SO depois que o usuário escolheu um tema manualmente', () => {
    const media = stubMatchMedia(false)
    render(<AppHeader />)

    fireEvent.click(getThemeButton()) // system -> light (manual)

    const applyThemeSpy = vi.spyOn(theme, 'applyTheme')
    media.fireChange(true)

    expect(applyThemeSpy).not.toHaveBeenCalled()
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
