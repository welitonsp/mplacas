import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import {
  executivePayload,
  financialReturnUnavailablePayload,
  jsonResponse,
  singlePlant,
} from '../../test/dashboardFixtures'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste (ver `LoginPage.test.tsx`,
// `DashboardPage.test.tsx`, `TechnicalPage.test.tsx`).
vi.mock('../../env', () => ({
  API_URL: 'https://api.example.test',
}))

// `FinancialPage` (e, transitivamente, `PlantProvider`/`AuthProvider` usados
// por `renderModule`) depende de 4 exports de `../../lib/api`: os dois
// recursos do módulo (`fetchExecutiveDashboard`, `fetchFinancialReturn`),
// `fetchPlants` (`PlantContext`), `configureApi` (`AuthContext`) e
// `updateFinancialConfiguration` (usado por `CapexRegistrationForm`, que
// `FinancialSection` monta quando o investimento ainda não foi registrado —
// resolve para o mesmo módulo `lib/api.ts` independentemente do caminho
// relativo usado em cada arquivo). Nenhum dos outros fetchers de
// `../../lib/api` (`fetchAnomalyHistory`, `fetchMonthlyProductionHistory`,
// `fetchPhotovoltaicSummary`) é importado por este módulo — se algum teste
// abaixo os disparasse, o mock (que não os declara) já provaria a fronteira
// de fetch por módulo (ADR-072, Decisão 3).
interface ApiMockOverrides {
  fetchExecutiveDashboard?: (plantId: string) => Promise<Response>
  fetchFinancialReturn?: (plantId: string) => Promise<Response>
  fetchPlants?: () => Promise<unknown[]>
  updateFinancialConfiguration?: (...args: unknown[]) => Promise<Response>
}

function installApiMock(overrides: ApiMockOverrides = {}) {
  vi.doMock('../../lib/api', () => ({
    fetchExecutiveDashboard:
      overrides.fetchExecutiveDashboard ?? vi.fn(async () => jsonResponse(executivePayload)),
    fetchFinancialReturn:
      overrides.fetchFinancialReturn ?? vi.fn(async () => jsonResponse(financialReturnUnavailablePayload)),
    fetchPlants: overrides.fetchPlants ?? vi.fn(async () => [singlePlant]),
    updateFinancialConfiguration:
      overrides.updateFinancialConfiguration ?? vi.fn(async () => jsonResponse({})),
    configureApi: vi.fn(),
  }))
}

async function renderFinancialPage() {
  const { FinancialPage } = await import('./FinancialPage')
  const { renderModule } = await import('../../test/renderModule')
  const { DASHBOARD_FINANCIAL_PATH } = await import('../../routes')
  return renderModule(<FinancialPage />, DASHBOARD_FINANCIAL_PATH)
}

describe('FinancialPage — módulo Financeiro (ADR-072, Etapa 3)', () => {
  it('dispara exatamente 2 requisições de dados — /energy/executive/latest e /energy/financial-return/latest, nenhuma outra', async () => {
    vi.resetModules()
    const fetchExecutiveMock = vi.fn(async () => jsonResponse(executivePayload))
    const fetchFinancialReturnMock = vi.fn(async () => jsonResponse(financialReturnUnavailablePayload))
    installApiMock({
      fetchExecutiveDashboard: fetchExecutiveMock,
      fetchFinancialReturn: fetchFinancialReturnMock,
    })

    await renderFinancialPage()

    // O `<h1>` "Financeiro" é renderizado assim que `plantId` resolve (ver
    // `FinancialPage.tsx`), antes de `usePlantResource` necessariamente já
    // ter disparado as duas requisições — sem `waitFor` ao redor das
    // asserções de contagem, esta checagem corre contra o efeito assíncrono
    // e falha de forma intermitente (achado durante ADR-072 Etapa 7,
    // reproduzido em `main` antes de qualquer mudança; mesmo padrão de
    // `OverviewPage.test.tsx`/`ProductionPage.test.tsx`, que já usam
    // `waitFor` para a asserção equivalente).
    await screen.findByText('Financeiro')
    await waitFor(() => {
      expect(fetchExecutiveMock).toHaveBeenCalledTimes(1)
      expect(fetchFinancialReturnMock).toHaveBeenCalledTimes(1)
    })
    expect(fetchExecutiveMock).toHaveBeenCalledWith(singlePlant.id)
    expect(fetchFinancialReturnMock).toHaveBeenCalledWith(singlePlant.id)
  })

  it('mostra o esqueleto de carregamento enquanto /energy/executive/latest está em voo, depois o conteúdo real (sucesso)', async () => {
    vi.resetModules()
    let resolveFetch: (value: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve
    })
    installApiMock({ fetchExecutiveDashboard: vi.fn(async () => pending) })

    await renderFinancialPage()

    // O `<h1>` do módulo (ADR-072, Etapa 6) aparece assim que o módulo monta
    // (depois de `PlantContext` resolver a usina, daí o `await findByRole`)
    // — deixou de ser sinal de dado carregado (era o único jeito de achar o
    // texto "Financeiro" antes desta etapa, quando só vinha de dentro de
    // `FinancialSection`). O conteúdo real (gated por `data && indicators`)
    // continua esperando `/energy/executive/latest`.
    expect(await screen.findByRole('heading', { level: 1, name: 'Financeiro' })).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { level: 2, name: 'Retorno do investimento' })
    ).not.toBeInTheDocument()

    resolveFetch(jsonResponse(executivePayload))

    expect(
      await screen.findByRole('heading', { level: 2, name: 'Retorno do investimento' })
    ).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*420,71/)).toBeInTheDocument()
    // Ciclo de referência (`current_cycle.reference_month`, achado F1 da
    // auditoria financeira desta sessão) visível junto de "Custo do ciclo" —
    // antes só aparecia em `HeroCard`, no módulo Visão Geral (outra rota).
    expect(screen.getByText('Ciclo de referência: 2026-07')).toBeInTheDocument()
  })

  it('em erro de /energy/executive/latest, mostra RetryableError e refaz o fetch ao clicar em "Tentar novamente"', async () => {
    vi.resetModules()
    const fetchExecutiveMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: 'boom' }, 500))
      .mockResolvedValueOnce(jsonResponse(executivePayload))
    installApiMock({ fetchExecutiveDashboard: fetchExecutiveMock })

    await renderFinancialPage()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Erro ao buscar dados.')
    expect(
      screen.queryByRole('heading', { level: 2, name: 'Retorno do investimento' })
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))

    await screen.findByRole('heading', { level: 2, name: 'Retorno do investimento' })
    expect(fetchExecutiveMock).toHaveBeenCalledTimes(2)
  })

  it('cadastro de CAPEX dispara financialReturn.refetch — uma nova chamada a fetchFinancialReturn depois do submit', async () => {
    vi.resetModules()
    const fetchFinancialReturnMock = vi.fn(async () => jsonResponse(financialReturnUnavailablePayload))
    const updateFinancialConfigurationMock = vi.fn(async () => jsonResponse({}))
    installApiMock({
      fetchFinancialReturn: fetchFinancialReturnMock,
      updateFinancialConfiguration: updateFinancialConfigurationMock,
    })

    await renderFinancialPage()

    // `unavailable_reason: 'INVESTMENT_NOT_REGISTERED'` (default do mock) faz
    // `FinancialReturnSection` renderizar `CapexRegistrationForm` — a única
    // escrita deste módulo.
    await screen.findByLabelText(/valor investido/i)
    expect(fetchFinancialReturnMock).toHaveBeenCalledTimes(1)

    fireEvent.change(screen.getByLabelText(/valor investido/i), { target: { value: '48000.00' } })
    fireEvent.click(screen.getByRole('button', { name: /cadastrar investimento/i }))

    await waitFor(() =>
      expect(updateFinancialConfigurationMock).toHaveBeenCalledWith(singlePlant.id, {
        investment_amount_brl: '48000.00',
      })
    )
    await waitFor(() => expect(fetchFinancialReturnMock).toHaveBeenCalledTimes(2))
  })
})
