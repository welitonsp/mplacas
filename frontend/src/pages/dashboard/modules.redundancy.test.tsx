import { describe, expect, it, vi } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import {
  anomalyPayload,
  executivePayload,
  financialReturnUnavailablePayload,
  jsonResponse,
  monthlyHistoryPayload,
  photovoltaicSummaryPayload,
  singlePlant,
} from '../../test/dashboardFixtures'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste (ver os demais testes de
// módulo em `pages/dashboard/*.test.tsx`).
vi.mock('../../env', () => ({
  API_URL: 'https://api.example.test',
}))

// Mock único cobrindo os fetchers dos 4 módulos — este arquivo não testa
// fronteira de fetch por módulo (já coberta, um a um, por
// `OverviewPage.test.tsx`/`ProductionPage.test.tsx`/`FinancialPage.test.tsx`/
// `TechnicalPage.test.tsx`); aqui importa só que os 4 módulos consigam
// carregar dado real para comparar o texto renderizado entre eles.
function installApiMock() {
  vi.doMock('../../lib/api', () => ({
    fetchExecutiveDashboard: vi.fn(async () => jsonResponse(executivePayload)),
    fetchAnomalyHistory: vi.fn(async () => jsonResponse(anomalyPayload)),
    fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(photovoltaicSummaryPayload)),
    fetchMonthlyProductionHistory: vi.fn(async () => jsonResponse(monthlyHistoryPayload)),
    fetchFinancialReturn: vi.fn(async () => jsonResponse(financialReturnUnavailablePayload)),
    fetchPlants: vi.fn(async () => [singlePlant]),
    updateFinancialConfiguration: vi.fn(async () => jsonResponse({})),
    configureApi: vi.fn(),
  }))
}

// `anomalyPayload` (`current_streak_days: 2`) é buscado tanto por
// `OverviewPage` (só para `latestDataDate`) quanto por `ProductionPage`, mas
// só `ProductionPage` repassa `current_streak_days` para
// `ProductionHistoryChart`, que é quem renderiza esta frase — ver
// `ProductionHistoryChart.tsx`. Antes da modularização (ADR-072), um teste em
// `DashboardPage.test.tsx` garantia que essa frase aparecia exatamente uma
// vez "na página inteira"; a asserção foi removida quando `DashboardPage`
// deixou de existir (ver ADR seção "Negativas") porque "a página inteira"
// deixou de fazer sentido com 4 rotas separadas. Este teste retoma a mesma
// garantia, adaptada para "no máximo um dos 4 módulos", montando cada módulo
// isoladamente em sequência (nunca simultaneamente — é assim que o usuário
// real os vê, um por vez, via `DashboardNav`).
const STREAK_PHRASE = /2 dias seguidos com produção abaixo do esperado\./

describe('Módulos do painel — sem redundância cross-módulo (ADR-072, Etapa 6)', () => {
  it('a frase de streak de dias consecutivos aparece só no módulo Produção, não nos outros 3', async () => {
    vi.resetModules()
    installApiMock()

    const { renderModule } = await import('../../test/renderModule')
    const {
      DASHBOARD_OVERVIEW_PATH,
      DASHBOARD_PRODUCTION_PATH,
      DASHBOARD_FINANCIAL_PATH,
      DASHBOARD_TECHNICAL_PATH,
    } = await import('../../routes')
    const { OverviewPage } = await import('./OverviewPage')
    const { ProductionPage } = await import('./ProductionPage')
    const { FinancialPage } = await import('./FinancialPage')
    const { TechnicalPage } = await import('./TechnicalPage')

    // Visão Geral: busca o mesmo `anomalyPayload`, mas só para
    // `latestDataDate` — a frase de streak não deve aparecer aqui.
    renderModule(<OverviewPage />, DASHBOARD_OVERVIEW_PATH)
    await screen.findByText('Origem do consumo — ciclo 2026-07')
    expect(screen.queryAllByText(STREAK_PHRASE)).toHaveLength(0)
    cleanup()

    // Produção: única dona legítima da frase.
    renderModule(<ProductionPage />, DASHBOARD_PRODUCTION_PATH)
    expect(await screen.findAllByText(STREAK_PHRASE)).toHaveLength(1)
    cleanup()

    // Financeiro: não busca `anomalies` nenhuma — a frase não pode aparecer.
    renderModule(<FinancialPage />, DASHBOARD_FINANCIAL_PATH)
    await screen.findByRole('heading', { level: 2, name: 'Retorno do investimento' })
    expect(screen.queryAllByText(STREAK_PHRASE)).toHaveLength(0)
    cleanup()

    // Técnico: idem, não busca `anomalies`.
    renderModule(<TechnicalPage />, DASHBOARD_TECHNICAL_PATH)
    await screen.findByText('Bruto')
    expect(screen.queryAllByText(STREAK_PHRASE)).toHaveLength(0)
    cleanup()
  })
})
