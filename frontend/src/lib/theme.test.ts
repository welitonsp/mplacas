import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resolveInitialTheme, setThemePreference, watchSystemTheme } from './theme'

const STORAGE_KEY = 'mplacas:theme'

/**
 * jsdom não implementa `matchMedia` — stub mínimo o suficiente para os dois
 * comportamentos que `theme.ts` depende: `.matches` (leitura síncrona) e
 * `addEventListener('change', ...)`/`removeEventListener` (mudança em tempo
 * real, usada por `watchSystemTheme`). Mesmo padrão de `vi.stubGlobal` já
 * usado em `AuthContext.test.tsx` para `fetch`.
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
    listenerCount: () => listeners.size,
  }
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  window.localStorage.clear()
  vi.unstubAllGlobals()
})

describe('resolveInitialTheme — ADR-071, Decisão 1/2', () => {
  it('override salvo "dark" vence, independente do matchMedia (SO diz claro)', () => {
    stubMatchMedia(false)
    window.localStorage.setItem(STORAGE_KEY, 'dark')

    expect(resolveInitialTheme()).toBe('dark')
  })

  it('override salvo "light" vence, independente do matchMedia (SO diz escuro)', () => {
    stubMatchMedia(true)
    window.localStorage.setItem(STORAGE_KEY, 'light')

    expect(resolveInitialTheme()).toBe('light')
  })

  it('ausência de chave + matchMedia escuro → retorna "dark"', () => {
    stubMatchMedia(true)

    expect(resolveInitialTheme()).toBe('dark')
  })

  it('ausência de chave + matchMedia claro → retorna "light"', () => {
    stubMatchMedia(false)

    expect(resolveInitialTheme()).toBe('light')
  })

  it.each(['blue', '', 'v1-legacy-value', 'Dark', 'LIGHT'])(
    'valor salvo inválido (%j) é ignorado, cai no matchMedia como se ausente',
    (invalidValue) => {
      stubMatchMedia(true)
      window.localStorage.setItem(STORAGE_KEY, invalidValue)

      expect(resolveInitialTheme()).toBe('dark')
    }
  )
})

describe('setThemePreference — ADR-071, Decisão 1', () => {
  it('"dark" grava a chave com o valor exato', () => {
    setThemePreference('dark')

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('dark')
  })

  it('"light" grava a chave com o valor exato', () => {
    setThemePreference('light')

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('light')
  })

  it('"system" remove a chave existente', () => {
    window.localStorage.setItem(STORAGE_KEY, 'dark')

    setThemePreference('system')

    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('"system" não lança e não grava nada quando a chave já não existia', () => {
    expect(() => setThemePreference('system')).not.toThrow()
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})

describe('watchSystemTheme — reage ao SO só enquanto não houver override salvo', () => {
  it('chama onChange com o novo tema quando o SO muda e não há override salvo', () => {
    const media = stubMatchMedia(false)
    const onChange = vi.fn()

    const cleanup = watchSystemTheme(onChange)
    media.fireChange(true)

    expect(onChange).toHaveBeenCalledWith('dark')
    cleanup()
  })

  it('não chama onChange quando existe um override salvo em localStorage', () => {
    const media = stubMatchMedia(false)
    window.localStorage.setItem(STORAGE_KEY, 'light')
    const onChange = vi.fn()

    const cleanup = watchSystemTheme(onChange)
    media.fireChange(true)

    expect(onChange).not.toHaveBeenCalled()
    cleanup()
  })

  it('a função de cleanup remove o listener (removeEventListener chamado)', () => {
    const media = stubMatchMedia(false)
    const onChange = vi.fn()

    const cleanup = watchSystemTheme(onChange)
    expect(media.listenerCount()).toBe(1)

    cleanup()
    expect(media.listenerCount()).toBe(0)

    media.fireChange(true)
    expect(onChange).not.toHaveBeenCalled()
  })
})
