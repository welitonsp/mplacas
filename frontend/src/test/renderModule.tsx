import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { AuthProvider } from '../contexts/AuthContext'
import { PlantProvider } from '../contexts/PlantContext'
import { DASHBOARD_TECHNICAL_PATH } from '../routes'

// Harness de render compartilhado pelos testes de módulo do painel
// (ADR-072, Etapa 2). Monta o elemento do módulo dentro do roteador, com a
// rota do módulo já ativa — necessário porque `PlantContext.selectPlant` usa
// `useSearchParams`, que exige um `Router` ancestral — envolvido no mesmo
// contexto que `DashboardLayout`/`App.tsx` fornecem em produção
// (`AuthProvider` + `PlantProvider`, este último busca `/plants` ao montar,
// ADR-069). `AppShell`/`DashboardNav` ficam de fora de propósito: os testes
// de módulo cobrem o conteúdo do módulo isoladamente, mesmo padrão já usado
// por `renderDashboard` em `DashboardPage.test.tsx` (que também renderiza só
// dentro de um `<main>` mínimo, sem a casca inteira do app).
//
// Este arquivo precisa ser importado dinamicamente (`await import(...)`)
// pelos testes que mockam `../lib/api` via `vi.doMock` — igual ao padrão já
// usado por `DashboardPage.test.tsx` para `DashboardPage`/`AuthProvider`/
// `PlantProvider`: um import estático no topo do arquivo de teste seria
// resolvido antes do `vi.doMock` surtir efeito.
//
// `path` é parametrizável para os próximos módulos (Financeiro, Produção,
// Visão Geral) reusarem este harness sem duplicá-lo — o default aponta para
// o módulo Técnico, o único migrado até agora.
export function renderModule(moduleElement: ReactElement, path: string = DASHBOARD_TECHNICAL_PATH) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <PlantProvider>
          <main>{moduleElement}</main>
        </PlantProvider>
      </AuthProvider>
    </MemoryRouter>
  )
}
