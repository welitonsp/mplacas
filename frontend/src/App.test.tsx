import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import {
  DASHBOARD_DEFAULT_PATH,
  DASHBOARD_FINANCIAL_PATH,
  DASHBOARD_PRODUCTION_PATH,
  DASHBOARD_ROOT_PATH,
  DASHBOARD_TECHNICAL_PATH,
} from './routes'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste (ver `LoginPage.test.tsx`).
vi.mock('./env', () => ({
  API_URL: 'https://api.example.test',
}))

const P1 = { id: '11111111-1111-1111-1111-111111111111', name: 'Usina 1', installedPowerKwp: null }
const P2 = { id: '22222222-2222-2222-2222-222222222222', name: 'Usina 2', installedPowerKwp: null }

// Todos os 5 recursos dos módulos do dashboard (Etapa 1 do ADR-072: os 4
// módulos renderizam seu conteúdo real) falham por padrão — o objetivo
// destes testes é a casca de rotas, não o conteúdo interno de cada módulo
// (já coberto pelos testes de cada módulo: `OverviewPage.test.tsx`,
// `ProductionPage.test.tsx`, `FinancialPage.test.tsx`, `TechnicalPage.test.tsx`).
// `usePlantResource` captura rejeição/erro internamente (nunca deixa a Promise
// sem `catch`, nunca lança), então isso só produz banners de erro na página —
// não derruba o teste.
function installApiMock(fetchPlantsImpl: () => Promise<unknown[]>) {
  vi.doMock('./lib/api', () => ({
    fetchExecutiveDashboard: vi.fn(async () => {
      throw new Error('mock: sem rede em App.test.tsx')
    }),
    fetchAnomalyHistory: vi.fn(async () => {
      throw new Error('mock: sem rede em App.test.tsx')
    }),
    fetchPhotovoltaicSummary: vi.fn(async () => {
      throw new Error('mock: sem rede em App.test.tsx')
    }),
    fetchFinancialReturn: vi.fn(async () => {
      throw new Error('mock: sem rede em App.test.tsx')
    }),
    fetchMonthlyProductionHistory: vi.fn(async () => {
      throw new Error('mock: sem rede em App.test.tsx')
    }),
    fetchPlants: fetchPlantsImpl,
    configureApi: vi.fn(),
  }))
}

async function renderApp(
  initialPath: string,
  { authenticated = true, plants = [P1] }: { authenticated?: boolean; plants?: unknown[] } = {}
) {
  vi.resetModules()
  const fetchPlants = vi.fn(async () => plants)
  installApiMock(fetchPlants)

  if (authenticated) {
    const { TokenStore } = await import('./lib/auth')
    TokenStore.set('fake-token')
  }

  window.history.pushState({}, '', initialPath)
  const { App } = await import('./App')
  const result = render(<App />)
  return { ...result, fetchPlants }
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('App — redirect de /dashboard preserva a query string (ADR-072, Decisão 1)', () => {
  it('/dashboard?plant=X → /dashboard/visao-geral?plant=X', async () => {
    await renderApp(`${DASHBOARD_ROOT_PATH}?plant=xpto-123`)

    await waitFor(() => {
      expect(window.location.pathname).toBe(DASHBOARD_DEFAULT_PATH)
    })
    expect(window.location.search).toBe('?plant=xpto-123')
  })

  it('sub-rota desconhecida (/dashboard/xpto) também redireciona para o módulo padrão', async () => {
    await renderApp(`${DASHBOARD_ROOT_PATH}/xpto`)

    await waitFor(() => {
      expect(window.location.pathname).toBe(DASHBOARD_DEFAULT_PATH)
    })
  })

  it('sub-rota desconhecida com query string também preserva a query string', async () => {
    await renderApp(`${DASHBOARD_ROOT_PATH}/xpto?plant=abc`)

    await waitFor(() => {
      expect(window.location.pathname).toBe(DASHBOARD_DEFAULT_PATH)
    })
    expect(window.location.search).toBe('?plant=abc')
  })
})

describe('App — PlantProvider não remonta ao navegar entre módulos', () => {
  it('fetchPlants é chamado exatamente 1 vez depois de navegar pelos 4 módulos em sequência', async () => {
    const { fetchPlants } = await renderApp(DASHBOARD_DEFAULT_PATH)

    await waitFor(() => expect(fetchPlants).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('link', { name: 'Produção' }))
    fireEvent.click(screen.getByRole('link', { name: 'Financeiro' }))
    fireEvent.click(screen.getByRole('link', { name: 'Técnico' }))
    fireEvent.click(screen.getByRole('link', { name: 'Visão Geral' }))

    await waitFor(() => expect(window.location.pathname).toBe(DASHBOARD_DEFAULT_PATH))
    expect(fetchPlants).toHaveBeenCalledTimes(1)
  })
})

describe('App — troca de usina preserva a rota atual', () => {
  it('trocar de usina em /dashboard/producao mantém o pathname, só muda ?plant=', async () => {
    await renderApp(DASHBOARD_PRODUCTION_PATH, { plants: [P1, P2] })

    const select = await screen.findByRole('combobox', { name: /usina ativa/i })
    await waitFor(() => expect(window.location.pathname).toBe(DASHBOARD_PRODUCTION_PATH))

    fireEvent.change(select, { target: { value: P2.id } })

    await waitFor(() => expect(window.location.search).toBe(`?plant=${P2.id}`))
    expect(window.location.pathname).toBe(DASHBOARD_PRODUCTION_PATH)
  })
})

describe('App — usuário deslogado é barrado nos 4 módulos', () => {
  const modulePaths = [DASHBOARD_DEFAULT_PATH, DASHBOARD_PRODUCTION_PATH, DASHBOARD_FINANCIAL_PATH, DASHBOARD_TECHNICAL_PATH]

  it.each(modulePaths)('%s redireciona para /login quando não autenticado', async (path) => {
    await renderApp(path, { authenticated: false })

    await waitFor(() => expect(window.location.pathname).toBe('/login'))
  })
})
