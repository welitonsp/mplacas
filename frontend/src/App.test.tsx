import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest'
import { cleanup, configure, fireEvent, render, screen, waitFor } from '@testing-library/react'
import {
  DASHBOARD_DEFAULT_PATH,
  DASHBOARD_FINANCIAL_PATH,
  DASHBOARD_PRODUCTION_PATH,
  DASHBOARD_ROOT_PATH,
  DASHBOARD_TECHNICAL_PATH,
} from './routes'

// Causa raiz confirmada por reprodução (não a hipótese original de "waitFor sem
// âncora determinística" — todas as âncoras deste arquivo já checam estado
// observável real). Cada teste chama `vi.resetModules()` + reimporta `./App`,
// forçando o registro de módulos do Vitest a reavaliar do zero toda a árvore de
// rotas `lazy()` (DashboardLayout, OverviewPage, ProductionPage, ...). O
// primeiro teste do arquivo — em ORDEM DE EXECUÇÃO, não necessariamente o
// primeiro do arquivo-fonte — a acionar um chunk específico paga o custo de
// transformação "fria" dessa importação dinâmica; os demais reaproveitam o
// módulo já transformado pelo Vite e são rápidos. `waitFor`/`findBy*` usam por
// padrão `asyncUtilTimeout: 1000` (`@testing-library/dom/dist/config.js`),
// **independente** de `testTimeout: 15000` (`vitest.config.ts`) — a mesma
// classe de problema que motivou aquele valor nunca chegou ao timeout interno
// do `waitFor`. Sob 84 arquivos rodando em paralelo (contenção de CPU) o custo
// frio ocasionalmente estoura 1000ms; reproduzido também isolado com
// `--sequence.shuffle`, onde a ordem aleatória muda qual teste paga o custo
// frio. Alinhar os dois timeouts fecha a lacuna sem afrouxar nenhuma asserção:
// um teste genuinamente travado ainda falha, agora em até 15s (o mesmo teto
// que `testTimeout` já impunha ao teste inteiro), não mais em 1s.
configure({ asyncUtilTimeout: 15000 })

// Cleanup também aqui, além do global em `src/test/setup.ts`: este arquivo
// remonta a árvore inteira do app a cada teste (`vi.resetModules()` +
// reimportação de `./App`), então desmontar explicitamente no próprio arquivo
// garante que nenhum app de um teste sobreviva no DOM do seguinte.
afterEach(cleanup)

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
//
// Mock fixo de `./lib/api`, registrado uma vez (hoisted). Cada teste troca só a
// implementação de `fetchPlants` em `apiMock`. Antes, cada teste chamava
// `vi.doMock('./lib/api', ...)` com uma fábrica nova; a partir do Vitest 5 a
// fábrica de um teste continuava valendo nos seguintes deste arquivo, mesmo com
// `vi.resetModules()` — o teste de troca de usina recebia a lista `[P1]` do teste
// anterior, nunca chamava o próprio `fetchPlants` e estourava o timeout à
// espera do seletor. Delegar para `apiMock` não depende desse comportamento.
const apiMock = vi.hoisted(() => ({
  fetchPlants: (async () => []) as () => Promise<unknown[]>,
}))

vi.mock('./lib/api', () => ({
  // A tela de login acorda a API ao abrir (plano grátis hiberna); sem rede aqui.
  warmUpApi: vi.fn(),
  fetchExecutiveDashboard: vi.fn(async () => {
    throw new Error('mock: sem rede em App.test.tsx')
  }),
  fetchAnomalyHistory: vi.fn(async () => {
    throw new Error('mock: sem rede em App.test.tsx')
  }),
  fetchPhotovoltaicSummary: vi.fn(async () => {
    throw new Error('mock: sem rede em App.test.tsx')
  }),
  fetchDeviceDailyStatus: vi.fn(async () => {
    throw new Error('mock: sem rede em App.test.tsx')
  }),
  fetchFinancialReturn: vi.fn(async () => {
    throw new Error('mock: sem rede em App.test.tsx')
  }),
  fetchMonthlyProductionHistory: vi.fn(async () => {
    throw new Error('mock: sem rede em App.test.tsx')
  }),
  fetchInvestorPanel: vi.fn(async () => {
    throw new Error('mock: sem rede em App.test.tsx')
  }),
  fetchPendingBills: vi.fn(async () => {
    throw new Error('mock: sem rede em App.test.tsx')
  }),
  fetchPlantNow: vi.fn(async () => new Response(JSON.stringify({ detail: 'plant_now_unavailable' }), { status: 404 })),
  fetchPlantSetup: vi.fn(async () => {
    throw new Error('mock: sem rede em App.test.tsx')
  }),
  uploadBillPdf: vi.fn(),
  confirmBill: vi.fn(),
  rejectBill: vi.fn(),
  fetchSavingsGaps: vi.fn(async () => new Response(JSON.stringify({ count: 0, items: [] }), { status: 200 })),
  reprocessSavingsGaps: vi.fn(),
  fetchPlants: () => apiMock.fetchPlants(),
  configureApi: vi.fn(),
}))

async function renderApp(
  initialPath: string,
  {
    authenticated = true,
    plants = [P1],
    refresh = () => new Response('{}', { status: 401 }),
  }: { authenticated?: boolean; plants?: unknown[]; refresh?: () => Response | Promise<Response> } = {}
) {
  vi.resetModules()
  // Só o transporte da sessão (`lib/session.ts`) usa `fetch` aqui: o resto da
  // API está mockado acima. Padrão: sem cookie de sessão (401).
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/auth/refresh')) return refresh()
    return new Response(null, { status: 204 })
  })
  vi.stubGlobal('fetch', fetchMock)
  const fetchPlants = vi.fn(async () => plants)
  apiMock.fetchPlants = fetchPlants

  if (authenticated) {
    const { TokenStore } = await import('./lib/auth')
    TokenStore.set('fake-token')
  }

  window.history.pushState({}, '', initialPath)
  const { App } = await import('./App')
  const result = render(<App />)
  return { ...result, fetchPlants, fetchMock }
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App — redirect de /dashboard preserva a query string (ADR-072, Decisão 1)', () => {
  it('/dashboard?plant=X → /dashboard/inicio?plant=X', async () => {
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
  it('fetchPlants é chamado exatamente 1 vez depois de navegar pelas 4 abas em sequência', async () => {
    const { fetchPlants } = await renderApp(DASHBOARD_DEFAULT_PATH)

    await waitFor(() => expect(fetchPlants).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('link', { name: 'Energia' }))
    fireEvent.click(screen.getByRole('link', { name: 'Dinheiro' }))
    fireEvent.click(screen.getByRole('link', { name: 'Minha usina' }))
    fireEvent.click(screen.getByRole('link', { name: 'Início' }))

    await waitFor(() => expect(window.location.pathname).toBe(DASHBOARD_DEFAULT_PATH))
    expect(fetchPlants).toHaveBeenCalledTimes(1)
  })
})

describe('App — troca de usina preserva a rota atual', () => {
  it('trocar de usina em /dashboard/energia mantém o pathname, só muda ?plant=', async () => {
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

describe('App — URLs da organização anterior redirecionam para a aba nova (ADR-083)', () => {
  it.each([
    ['visao-geral', DASHBOARD_DEFAULT_PATH],
    ['producao', DASHBOARD_PRODUCTION_PATH],
    ['financeiro', DASHBOARD_FINANCIAL_PATH],
    ['tecnico', DASHBOARD_TECHNICAL_PATH],
  ])('/dashboard/%s?plant=X → %s?plant=X', async (segment, target) => {
    await renderApp(`${DASHBOARD_ROOT_PATH}/${segment}?plant=${P1.id}`)

    await waitFor(() => expect(window.location.pathname).toBe(target))
    expect(window.location.search).toBe(`?plant=${P1.id}`)
  })
})

// ADR-102: a sessão sobrevive ao recarregar. Um carregamento completo (F5, link
// direto, aba nova) começa sem token em memória e pergunta ao servidor pelo
// cookie antes de decidir mandar ao login.
describe('App — sessão restaurada pelo cookie ao recarregar (ADR-102)', () => {
  it('recarregar num link profundo com cookie válido continua logado no mesmo link', async () => {
    const { fetchMock } = await renderApp(`${DASHBOARD_FINANCIAL_PATH}?plant=${P1.id}`, {
      authenticated: false,
      refresh: () => new Response(JSON.stringify({ access_token: 'restaurado' }), { status: 200 }),
    })

    expect(await screen.findByRole('link', { name: 'Dinheiro' })).toBeInTheDocument()
    expect(window.location.pathname).toBe(DASHBOARD_FINANCIAL_PATH)
    expect(window.location.search).toBe(`?plant=${P1.id}`)
    const refreshCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/auth/refresh'))
    expect(refreshCalls).toHaveLength(1)
    const init = refreshCalls[0]?.[1] as RequestInit
    expect(init.body).toBeUndefined()
    expect(init.credentials).toBe('same-origin')
    expect(new Headers(init.headers).get('X-Mplacas-Auth')).toBe('1')
  })

  it('recarregar sem cookie vai ao login sem "sessão encerrada" e guarda o destino', async () => {
    await renderApp(DASHBOARD_FINANCIAL_PATH, { authenticated: false })

    expect(await screen.findByRole('heading', { level: 1, name: 'Entrar no MPlacas' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/login')
    expect(screen.queryByText(/sessão foi encerrada/)).not.toBeInTheDocument()
  })

  it('enquanto pergunta, mostra "Conectando…" e não manda ao login; depois de 10 s explica o servidor acordando', async () => {
    let answer: (response: Response) => void = () => undefined
    await renderApp(DASHBOARD_DEFAULT_PATH, {
      authenticated: false,
      refresh: () => new Promise<Response>((resolve) => { answer = resolve }),
    })

    expect(await screen.findByText('Conectando…')).toBeInTheDocument()
    expect(window.location.pathname).toBe(DASHBOARD_DEFAULT_PATH)
    expect(screen.queryByText(/servidor está acordando/)).not.toBeInTheDocument()

    expect(
      await screen.findByText('O servidor está acordando, pode levar até um minuto.', undefined, { timeout: 12_000 })
    ).toBeInTheDocument()
    expect(window.location.pathname).toBe(DASHBOARD_DEFAULT_PATH)

    answer(new Response(JSON.stringify({ access_token: 'restaurado' }), { status: 200 }))
    expect(await screen.findByRole('link', { name: 'Início' })).toBeInTheDocument()
    expect(window.location.pathname).toBe(DASHBOARD_DEFAULT_PATH)
  }, 20_000)

  it('falha de rede oferece "Tentar de novo" em vez do login, e a nova tentativa entra', async () => {
    let attempt = 0
    await renderApp(DASHBOARD_PRODUCTION_PATH, {
      authenticated: false,
      refresh: () => {
        attempt += 1
        if (attempt === 1) throw new TypeError('Failed to fetch')
        return new Response(JSON.stringify({ access_token: 'restaurado' }), { status: 200 })
      },
    })

    const retry = await screen.findByRole('button', { name: 'Tentar de novo' })
    expect(window.location.pathname).toBe(DASHBOARD_PRODUCTION_PATH)

    fireEvent.click(retry)

    expect(await screen.findByRole('link', { name: 'Energia' })).toBeInTheDocument()
    expect(window.location.pathname).toBe(DASHBOARD_PRODUCTION_PATH)
  })

  it('servidor fora (504 do proxy) também oferece "Tentar de novo"', async () => {
    await renderApp(DASHBOARD_DEFAULT_PATH, {
      authenticated: false,
      refresh: () => new Response('{}', { status: 504 }),
    })

    expect(await screen.findByRole('button', { name: 'Tentar de novo' })).toBeInTheDocument()
    expect(window.location.pathname).toBe(DASHBOARD_DEFAULT_PATH)
  })
})
