import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { anomalyPayload, executivePayload, jsonResponse, singlePlant } from '../../test/dashboardFixtures'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste (ver `LoginPage.test.tsx`,
// `OverviewPage.test.tsx`).
vi.mock('../../env', () => ({
  API_URL: 'https://api.example.test',
}))

// Antes desta etapa (ADR-072, Etapa 5), este teste lia `DashboardPage.tsx?raw`
// e fazia regex na fonte para achar a `className` do botão "Atualizar" — a
// justificativa original era que `DashboardPage` faz fetch de dados reais no
// mount, então um render completo exigiria mockar rede só para inspecionar
// uma classe CSS estática, e jsdom não aplica foco de verdade
// (`:focus-visible` não é simulável sem um navegador real). O ADR já
// sinalizava que esse teste baseado em regex sobre `?raw` quebraria nesta
// etapa, quando `DashboardPage.tsx` deixasse de existir.
//
// Agora que o harness de módulo (`renderModule`, `dashboardFixtures`) já
// mocka os dois recursos deste módulo de forma padronizada (mesmo usado por
// `OverviewPage.test.tsx`), o custo de mockar rede deixou de ser um motivo
// para preferir regex sobre a fonte — o teste abaixo renderiza `OverviewPage`
// de verdade e verifica a `className` estática do botão real no DOM (as
// classes Tailwind de `focus-visible:` são sempre literais no atributo
// `class`, é só a pseudo-classe CSS que ativa a `:focus-visible` de fato — a
// ausência de foco simulável em jsdom não impede a checagem sobre a classe
// já presente). Continua indireto (checa a classe, não o foco de fato) —
// mesma limitação de antes, só que sobre o componente renderizado, não sobre
// a fonte crua.
function installApiMock() {
  vi.doMock('../../lib/api', () => ({
    fetchExecutiveDashboard: vi.fn(async () => jsonResponse(executivePayload)),
    fetchAnomalyHistory: vi.fn(async () => jsonResponse(anomalyPayload)),
    fetchPlants: vi.fn(async () => [singlePlant]),
    configureApi: vi.fn(),
  }))
}

describe('OverviewPage — botão "Atualizar" tem foco visível', () => {
  it('a className do botão "Atualizar" inclui focus-visible:ring', async () => {
    vi.resetModules()
    installApiMock()

    const { OverviewPage } = await import('./OverviewPage')
    const { renderModule } = await import('../../test/renderModule')
    const { DASHBOARD_OVERVIEW_PATH } = await import('../../routes')
    renderModule(<OverviewPage />, DASHBOARD_OVERVIEW_PATH)

    // A classe de foco é a mesma durante o carregamento. Não espere os dois
    // recursos terminarem apenas para inspecionar uma propriedade estática
    // do botão; isso torna o teste independente da velocidade do runner.
    const button = await screen.findByRole('button', { name: /Atualizar/ })
    expect(button.className).toMatch(/focus-visible:ring/)
  })
})
