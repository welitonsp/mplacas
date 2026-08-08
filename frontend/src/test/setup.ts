import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// `test.globals: false` em vitest.config.ts desliga o registro automático de
// `afterEach` que @testing-library/react faz por padrão — sem isso, o DOM de um
// teste vaza para o próximo `render()` no mesmo arquivo (consultas `queryByText`
// que verificam ausência passam a encontrar elementos do teste anterior).
afterEach(cleanup)

// jsdom não implementa `matchMedia` (`window.matchMedia` é `undefined`).
// `AppHeader` (ADR-071, controle de aparência) chama `matchMedia` já no
// primeiro render (via `watchSystemTheme`, enquanto a preferência ativa for
// "Sistema" — o default), então qualquer teste que monte `AppHeader` direto
// ou indireto (ex.: `AppShell`) lançaria `TypeError: window.matchMedia is
// not a function` sem este stub global mínimo. Testes que precisam simular
// mudança de preferência do SO (`theme.test.ts`, `AppHeader.test.tsx`)
// substituem este stub localmente por um mais completo via
// `vi.stubGlobal('matchMedia', ...)`, restaurado automaticamente por
// `vi.unstubAllGlobals()` no fim de cada teste.
if (typeof window.matchMedia !== 'function') {
  window.matchMedia = vi.fn((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia
}
