import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { anomalyPayload, executivePayload, jsonResponse, singlePlant } from '../test/dashboardFixtures'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste (ver `LoginPage.test.tsx`).
vi.mock('../env', () => ({
  API_URL: 'https://api.example.test',
}))

// `executivePayload`/`anomalyPayload` moram em `../test/dashboardFixtures.ts`
// desde as Etapas 3-4 do ADR-072 (extraídos para serem reusados por
// `FinancialPage.test.tsx`/`ProductionPage.test.tsx`) — importados no topo
// deste arquivo. `DashboardPage` (agora só o módulo Visão Geral, ADR-072
// Etapa 4) continua buscando os dois: `executive` para o corpo principal e
// `anomalies` só para `latestDataDate` (consumido pelo `HeroCard`) — o
// restante do que `anomalies` alimentava (histórico diário, produção do
// último dia, produção por ciclo de faturamento) migrou para
// `pages/dashboard/ProductionPage.tsx`, que tem sua própria instância desses
// recursos (`ProductionPage.test.tsx` cobre esses casos agora).

// Helper único de mock de `../lib/api` (Etapa 0: antes existiam 4 blocos
// `vi.doMock('../lib/api', ...)` divergentes — este `installApiMock` mais o
// `renderDashboard` abaixo, mais 3 blocos inline em testes específicos — cada
// um redefinindo os 6 exports do módulo do zero, sem nenhum incluir
// `fetchMonthlyProductionHistory`). Todos os pontos de mock da suíte passam a
// chamar esta função: os testes felizes usam só o default de cada export: os
// poucos testes que precisam de um comportamento diferente (contagem de
// chamadas, path/plant_id capturado, payload alternativo) sobrescrevem
// exatamente o export que importa via `overrides`, sem duplicar os outros.
// `fetchFinancialReturn` saiu deste mock na Etapa 3 do ADR-072 (seção
// financeira migrada para `FinancialPage`); `fetchPhotovoltaicSummary` e
// `fetchMonthlyProductionHistory` saíram na Etapa 4 (seção de produção
// migrada para `ProductionPage`) — `DashboardPage` não importa mais nenhum
// dos dois.
interface ApiMockOverrides {
  // Atalho para o caso mais comum (só o corpo de `/energy/executive/latest`
  // muda) — equivalente ao antigo parâmetro posicional de `installApiMock`/
  // `renderDashboard`. Ignorado se `fetchExecutiveDashboard` também for
  // informado.
  executivePayload?: unknown
  fetchExecutiveDashboard?: (plantId: string) => Promise<Response>
  fetchAnomalyHistory?: (plantId: string, days?: number) => Promise<Response>
  fetchPlants?: () => Promise<unknown[]>
  configureApi?: (...args: unknown[]) => void
}

function installApiMock(overrides: ApiMockOverrides = {}) {
  const executiveOverride = overrides.executivePayload ?? executivePayload
  vi.doMock('../lib/api', () => ({
    fetchExecutiveDashboard:
      overrides.fetchExecutiveDashboard ?? vi.fn(async () => jsonResponse(executiveOverride)),
    fetchAnomalyHistory:
      overrides.fetchAnomalyHistory ?? vi.fn(async () => jsonResponse(anomalyPayload)),
    fetchPlants: overrides.fetchPlants ?? vi.fn(async () => [singlePlant]),
    configureApi: overrides.configureApi ?? vi.fn(),
  }))
}

async function renderDashboard(executiveOverride: unknown = executivePayload) {
  installApiMock({ executivePayload: executiveOverride })
  const { DashboardPage } = await import('./DashboardPage')
  const { AuthProvider } = await import('../contexts/AuthContext')
  const { PlantProvider } = await import('../contexts/PlantContext')

  // `DashboardPage` não renderiza mais sua própria casca — o `<main>` (e o
  // container/padding) agora vive em `AppShell` (Frente S). Os testes abaixo
  // seguem verificando o conteúdo da página em relação a um `<main>`
  // ancestral, então o harness precisa fornecer um, sem trazer `AppShell`
  // inteiro (que exigiria mockar o menu de usuário) — só a estrutura mínima
  // que os seletores usam.
  const result = render(
    <MemoryRouter>
      <AuthProvider>
        <PlantProvider>
          <main>
            <DashboardPage />
          </main>
        </PlantProvider>
      </AuthProvider>
    </MemoryRouter>
  )
  // `PlantContext` resolve a usina de forma assíncrona (busca `/plants`) —
  // espera a página sair do esqueleto de carregamento antes de prosseguir.
  await screen.findByText('Atualizar')
  return result
}

describe('DashboardPage — reorganização em três blocos (Etapa 5)', () => {
  // ADR-072 Etapa 4: o teste do bullet chart "Produção do último dia vs.
  // esperada" e o teste do streak dentro de "Histórico de produção" foram
  // removidos daqui — as duas seções migraram para
  // `pages/dashboard/ProductionPage.tsx`. Cobertura equivalente do bullet
  // chart já existe em `components/LatestDailyProductionCard.test.tsx`
  // ("compara a produção real do último dia com dado contra a esperada do
  // mesmo dia"); o streak dentro do histórico ganhou um teste dedicado em
  // `pages/dashboard/ProductionPage.test.tsx`.

  it('autoconsumo/injetada/importada aparecem em um único componente de visualização (EnergyFlowDiagram)', async () => {
    vi.resetModules()
    await renderDashboard()

    // O diagrama de fluxo é o único visual mantido — os outros dois visuais
    // redundantes (composição em barra e donut de origem do consumo) não
    // devem aparecer na página.
    expect(await screen.findByText('Fluxo de energia no ciclo')).toBeInTheDocument()
    expect(screen.queryByText('Composição da produção')).not.toBeInTheDocument()
    expect(screen.queryByText('Origem do consumo')).not.toBeInTheDocument()
  })

  // Etapa 7 (histórico): o conteúdo detalhado do bloco financeiro
  // (decomposição da fatura, subgrupos "Custo do ciclo"/"Tarifas"/"Créditos
  // de energia", retorno do investimento) foi extraído para `FinancialSection`
  // nesta página, e cobria aqui um teste mínimo de integração (`indicators`/
  // `financialReturn` chegando intactos à seção extraída). ADR-072, Etapa 3:
  // `FinancialSection` saiu de `DashboardPage` de vez, migrada para o módulo
  // `pages/dashboard/FinancialPage.tsx` — a cobertura equivalente (payload
  // executivo/retorno do investimento chegando intactos à seção) agora vive
  // em `FinancialPage.test.tsx`, não mais aqui.

  it('unifica autossuficiência e dependência da rede em uma única StackedBar de 2 segmentos somando 100%', async () => {
    vi.resetModules()
    await renderDashboard()

    await screen.findByText('Indicadores percentuais')

    const bar = screen.getByRole('img', { name: /Total 100%/ })
    expect(bar).toHaveAttribute(
      'aria-label',
      'Total 100%: Autossuficiência 77,7%, Dependência da rede 22,3%',
    )

    expect(screen.getByText('Autossuficiência')).toBeInTheDocument()
    expect(screen.getByText('Dependência da rede')).toBeInTheDocument()
    expect(screen.getAllByText('77,7%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('22,3%').length).toBeGreaterThan(0)
  })
})

describe('DashboardPage — desredundância (Etapa 1.4)', () => {
  // ADR-072 Etapa 4: "a frase de streak de anomalia aparece exatamente uma
  // vez na página" foi removido — deixou de fazer sentido depois que a
  // página deixou de renderizar o histórico de produção (onde a frase
  // aparecia). A asserção de unicidade "na página inteira" era específica do
  // `DashboardPage` monolítico (ver ADR-072, seção "Negativas": um teste
  // cruzando os 4 módulos ficaria a cargo de uma etapa futura de
  // consolidação, se a duplicação entre módulos precisar ser reverificada).

  it('não renderiza mais a seção "Energia e produção" (redundante com o diagrama de fluxo)', async () => {
    vi.resetModules()
    await renderDashboard()

    await screen.findByText('Indicadores percentuais')

    expect(screen.queryByText('Energia e produção')).not.toBeInTheDocument()
    // Os mesmos fatos continuam visíveis, só que uma única vez, no diagrama de fluxo.
    expect(screen.getByText('Fluxo de energia no ciclo')).toBeInTheDocument()
  })

  it('importada, injetada, autoconsumo e consumo aparecem em uma única visualização — nenhum card avulso duplica os rótulos de "Energia e produção" removidos (Etapa 3.3)', async () => {
    vi.resetModules()
    await renderDashboard()

    await screen.findByText('Indicadores percentuais')

    // `EnergyProductionSection` (removida da composição na Etapa 1.4) usava
    // exatamente estes quatro rótulos em cards isolados — se algum deles
    // reaparecer na página fora do diagrama de fluxo, o fato voltou a ser
    // duplicado (P2-01). O diagrama em si (`EnergyFlowDiagram`) é uma única
    // visualização e, por design de fluxo (sankey), repete o valor de um
    // mesmo fato quando ele é ao mesmo tempo saída de um nó e entrada de
    // outro (ex.: "Exportada" sai de Produção e entra em Rede) — isso não é
    // a duplicação que a Etapa 3.3 elimina.
    expect(screen.queryByText('Energia importada')).not.toBeInTheDocument()
    expect(screen.queryByText('Energia injetada')).not.toBeInTheDocument()
    expect(screen.queryByText('Autoconsumo estimado')).not.toBeInTheDocument()
    expect(screen.queryByText('Consumo total estimado')).not.toBeInTheDocument()

    // Os quatro fatos continuam visíveis, todos dentro do único diagrama de
    // fluxo — valores do payload: imported=120, injected=80,
    // self_consumption=420, total_consumption=540.
    const flowSectionTitle = screen.getByText('Fluxo de energia no ciclo')
    const flowSection = flowSectionTitle.closest('div') as HTMLElement
    expect(within(flowSection).getAllByText(/120 kWh/).length).toBeGreaterThan(0)
    expect(within(flowSection).getAllByText(/80 kWh/).length).toBeGreaterThan(0)
    expect(within(flowSection).getAllByText(/420 kWh/).length).toBeGreaterThan(0)
    expect(within(flowSection).getAllByText(/540 kWh/).length).toBeGreaterThan(0)

    // E não aparecem duplicados fora dele, em nenhum outro card da página.
    const outsideFlow = document.body
    const allOccurrences = (pattern: RegExp) =>
      within(outsideFlow).getAllByText(pattern).filter((el) => !flowSection.contains(el))
    expect(allOccurrences(/^120 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^80 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^420 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^540 kWh$/)).toHaveLength(0)
  })
})

describe('DashboardPage — erro global tem retry associado (Etapa 1.6c)', () => {
  it('mostra "Tentar novamente" junto do erro e refaz o fetch ao clicar', async () => {
    vi.resetModules()
    let executiveCalls = 0
    installApiMock({
      fetchExecutiveDashboard: vi.fn(async () => {
        executiveCalls += 1
        if (executiveCalls === 1) return jsonResponse({ error: 'boom' }, 500)
        return jsonResponse(executivePayload)
      }),
    })

    const { DashboardPage } = await import('./DashboardPage')
    const { AuthProvider } = await import('../contexts/AuthContext')
    const { PlantProvider } = await import('../contexts/PlantContext')
    const { getByRole, findByRole, findByText } = render(
      <MemoryRouter>
        <AuthProvider>
          <PlantProvider>
            <DashboardPage />
          </PlantProvider>
        </AuthProvider>
      </MemoryRouter>
    )

    const alert = await findByRole('alert')
    expect(alert).toHaveTextContent(/Erro ao buscar dados/)

    const retryButton = getByRole('button', { name: 'Tentar novamente' })
    retryButton.click()

    await findByText('Indicadores percentuais')
    expect(executiveCalls).toBe(2)
  })

  // Etapa 6: antes, o retry do erro global refazia só o fetch executivo
  // (`executive.refetch`) — os outros recursos ficavam presos no estado
  // antigo mesmo depois do usuário pedir para tentar de novo. Prova que os 2
  // recursos que restam neste módulo (`executive`, `anomalies`) são refeitos
  // juntos (`refreshAll`), não só o que errou. Reduzido de 4 para 2 na Etapa
  // 4 do ADR-072: `pvSummaryResource`/`monthlyHistory` saíram deste módulo
  // (migrados para `ProductionPage`).
  it('refaz os 2 fetches (não só o executivo) ao clicar em "Tentar novamente" no erro global', async () => {
    vi.resetModules()
    let executiveCalls = 0
    const fetchAnomalyHistoryMock = vi.fn(async () => jsonResponse(anomalyPayload))
    installApiMock({
      fetchExecutiveDashboard: vi.fn(async () => {
        executiveCalls += 1
        if (executiveCalls === 1) return jsonResponse({ error: 'boom' }, 500)
        return jsonResponse(executivePayload)
      }),
      fetchAnomalyHistory: fetchAnomalyHistoryMock,
    })

    const { DashboardPage } = await import('./DashboardPage')
    const { AuthProvider } = await import('../contexts/AuthContext')
    const { PlantProvider } = await import('../contexts/PlantContext')
    const { getByRole, findByRole, findByText } = render(
      <MemoryRouter>
        <AuthProvider>
          <PlantProvider>
            <DashboardPage />
          </PlantProvider>
        </AuthProvider>
      </MemoryRouter>
    )

    await findByRole('alert')
    await waitFor(() => {
      expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(1)
    })

    const retryButton = getByRole('button', { name: 'Tentar novamente' })
    retryButton.click()

    await findByText('Indicadores percentuais')
    expect(executiveCalls).toBe(2)
    await waitFor(() => {
      expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(2)
    })
  })
})

describe('DashboardPage — grid real no breakpoint md (Etapa 1.2)', () => {
  it('pelo menos duas seções distintas declaram md:col-span diferente de 6 (grid de 6 colunas)', async () => {
    vi.resetModules()
    const { container } = await renderDashboard()

    await screen.findByText('Indicadores percentuais')

    const sections = Array.from(container.querySelectorAll('main > div.grid > section'))
    expect(sections.length).toBeGreaterThan(0)

    const nonFullWidthAtMd = sections.filter((section) => {
      const match = section.className.match(/\bmd:col-span-(\d+)\b/)
      return match !== null && match[1] !== '6'
    })

    // O grid de página é `md:grid-cols-6` — uma seção com `md:col-span-6` (ou
    // sem span declarado) ocupa a largura inteira, igual ao empilhamento de
    // mobile. Pelo menos duas seções precisam declarar um span menor no
    // breakpoint `md` para o tablet deixar de ser uma coluna única (P1-04).
    expect(nonFullWidthAtMd.length).toBeGreaterThanOrEqual(2)
  })
})

// ADR-072 Etapa 4: os três `describe` a seguir foram migrados por inteiro
// para `pages/dashboard/ProductionPage.test.tsx` — "re-busca dados quando a
// usina ativa muda" (lá com cobertura ampliada para os 3 recursos do módulo
// Produção), "histórico de produção não depende mais do baseline sazonal" (2
// testes) e a seção "Produção por ciclo de faturamento" (2 testes). O
// conteúdo que os três exercitavam (`ProductionHistorySection`,
// `LatestDailyProductionCard`, `MonthlyProductionSection`) não é mais
// renderizado por `DashboardPage`.
