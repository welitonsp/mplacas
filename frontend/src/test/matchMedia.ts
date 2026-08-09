import { vi } from 'vitest'

/**
 * Stub de `window.matchMedia` para testes que precisam controlar o
 * resultado de UMA media query específica (hoje só usado para
 * `prefers-reduced-motion: reduce`, ver `useChartEntrance`).
 *
 * jsdom não implementa `matchMedia` de verdade — o stub global mínimo de
 * `test/setup.ts` sempre devolve `matches: false` para qualquer query, o
 * que já é suficiente para o caso "sem preferência de movimento reduzido".
 * Este helper substitui esse stub globalmente (via `vi.stubGlobal`, mesmo
 * padrão de `theme.test.ts`/`AppHeader.test.tsx`) só quando um teste precisa
 * simular `matches: true`. Chame `vi.unstubAllGlobals()` no `afterEach` do
 * arquivo de teste para restaurar o stub padrão entre testes.
 */
export function stubMatchMediaMatches(matches: boolean): void {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  )
}
