import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import {
  anomalyPayload,
  executivePayload,
  jsonResponse,
  singlePlant,
} from '../../test/dashboardFixtures'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste (ver `LoginPage.test.tsx`,
// `FinancialPage.test.tsx`, `TechnicalPage.test.tsx`, `ProductionPage.test.tsx`).
vi.mock('../../env', () => ({
  API_URL: 'https://api.example.test',
}))

// `OverviewPage` (e, transitivamente, `PlantProvider`/`AuthProvider` usados
// por `renderModule`) depende de 4 exports de `../../lib/api`: os dois
// recursos do módulo (`fetchExecutiveDashboard`, `fetchAnomalyHistory`),
// `fetchPlants` (`PlantContext`) e `configureApi` (`AuthContext`). Nenhum dos
// outros fetchers de `../../lib/api` (`fetchFinancialReturn`,
// `fetchPhotovoltaicSummary`, `fetchMonthlyProductionHistory`) é importado por
// este módulo — se algum teste abaixo os disparasse, o mock (que não os
// declara) já provaria a fronteira de fetch por módulo (ADR-072, Decisão 3).
interface ApiMockOverrides {
  // Atalho para o caso mais comum (só o corpo de `/energy/executive/latest`
  // muda).
  executivePayload?: unknown
  fetchExecutiveDashboard?: (plantId: string) => Promise<Response>
  fetchAnomalyHistory?: (plantId: string, days?: number) => Promise<Response>
  fetchPlants?: () => Promise<unknown[]>
}

function installApiMock(overrides: ApiMockOverrides = {}) {
  const executiveOverride = overrides.executivePayload ?? executivePayload
  vi.doMock('../../lib/api', () => ({
    fetchExecutiveDashboard:
      overrides.fetchExecutiveDashboard ?? vi.fn(async () => jsonResponse(executiveOverride)),
    fetchAnomalyHistory:
      overrides.fetchAnomalyHistory ?? vi.fn(async () => jsonResponse(anomalyPayload)),
    fetchPlants: overrides.fetchPlants ?? vi.fn(async () => [singlePlant]),
    configureApi: vi.fn(),
  }))
}

async function renderOverviewPage() {
  const { OverviewPage } = await import('./OverviewPage')
  const { renderModule } = await import('../../test/renderModule')
  const { DASHBOARD_OVERVIEW_PATH } = await import('../../routes')
  return renderModule(<OverviewPage />, DASHBOARD_OVERVIEW_PATH)
}

describe('OverviewPage — módulo Visão Geral (ADR-072, Etapa 5)', () => {
  it('dispara exatamente 2 requisições de dados — /energy/executive/latest e /energy/anomalies/latest, nenhuma outra', async () => {
    vi.resetModules()
    const fetchExecutiveMock = vi.fn(async () => jsonResponse(executivePayload))
    const fetchAnomalyHistoryMock = vi.fn(async () => jsonResponse(anomalyPayload))
    installApiMock({
      fetchExecutiveDashboard: fetchExecutiveMock,
      fetchAnomalyHistory: fetchAnomalyHistoryMock,
    })

    await renderOverviewPage()

    await screen.findByRole('group', { name: 'Origem do consumo — ciclo 2026-07' })
    await waitFor(() => {
      expect(fetchExecutiveMock).toHaveBeenCalledTimes(1)
      expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(1)
    })
    expect(fetchExecutiveMock).toHaveBeenCalledWith(singlePlant.id)
    expect(fetchAnomalyHistoryMock).toHaveBeenCalledWith(singlePlant.id)
  })

  it('abre a Visão Geral com produção como indicador chave, confiança compacta e menos ruído acima da dobra', async () => {
    vi.resetModules()
    installApiMock()

    const { container } = await renderOverviewPage()

    const productionHero = await screen.findByRole('region', { name: 'Produção e saúde da usina' })
    expect(within(productionHero).getByRole('heading', { level: 2, name: 'Produção dos últimos 7 dias' })).toBeInTheDocument()
    expect(within(productionHero).getByText('Indicador chave')).toBeInTheDocument()
    expect(within(productionHero).getByText('Aguardando dados')).toBeInTheDocument()
    expect(within(productionHero).getByTestId('production-health-confidence-badge')).toHaveTextContent('Alta confiança · ciclo 2026-07')
    expect(within(productionHero).getByText('Próxima ação')).toBeInTheDocument()
    expect(within(productionHero).getByText('Coletar mais dados')).toBeInTheDocument()
    expect(within(productionHero).getByText('Média 7 dias')).toBeInTheDocument()
    expect(within(productionHero).getByText('Total 7 dias')).toBeInTheDocument()
    // "Último dia" e "Desempenho vs esperado" moraram aqui e na linha de
    // indicadores ao mesmo tempo; agora só na linha de indicadores.
    expect(within(productionHero).queryByText('Último dia')).not.toBeInTheDocument()
    expect(within(productionHero).queryByText('Desempenho vs esperado')).not.toBeInTheDocument()
    const kpis = screen.getByRole('group', { name: 'Resumo executivo do ciclo' })
    expect(within(kpis).getByText('Desempenho vs esperado')).toBeInTheDocument()
    expect(within(kpis).getByText('88,6')).toBeInTheDocument()
    expect(within(productionHero).getByRole('link', { name: /Abrir análise completa/ })).toHaveAttribute('href', '/dashboard/producao')
    const miniBars = within(productionHero).getAllByTestId('production-health-mini-bar')
    expect(miniBars.map((bar) => bar.getAttribute('data-severity'))).toEqual(['warning', 'success'])

    expect(screen.queryByRole('region', { name: 'Confiança dos dados do ciclo' })).not.toBeInTheDocument()
    expect(screen.queryByText('Pergunta')).not.toBeInTheDocument()
    expect(screen.queryByText('Saída')).not.toBeInTheDocument()

    const decisionSection = await screen.findByRole('region', { name: 'Decisão executiva do ciclo' })
    expect(within(decisionSection).getByRole('heading', { level: 2, name: 'Ciclo pede acompanhamento' })).toBeInTheDocument()
    expect(within(decisionSection).getByText('Acompanhar hoje')).toBeInTheDocument()
    expect(within(decisionSection).getByText('Próxima ação')).toBeInTheDocument()
    expect(within(decisionSection).queryByRole('group', { name: 'Sinais usados na decisão' })).not.toBeInTheDocument()

    // Ordem de leitura (ADR-077): resumo → indicadores → produção recente →
    // decisão → diagnósticos.
    const band = container.querySelector('[data-testid="hero-band"]') as HTMLElement
    const sections = Array.from(container.querySelectorAll('main > div.flex > section'))
    expect(sections[0]).toBe(band)
    expect(sections[1]).toBe(productionHero)
    expect(sections[2]).toBe(decisionSection)
    expect(band.compareDocumentPosition(kpis) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(kpis.compareDocumentPosition(productionHero) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('mantém confiança dos dados como seção grande só quando há ressalva de qualidade', async () => {
    vi.resetModules()
    installApiMock({
      executivePayload: {
        ...executivePayload,
        current_cycle: {
          ...executivePayload.current_cycle,
          quality: { missing_days: 1, provisional_days: 0, incomplete_days: 0, unavailable_days: 0 },
        },
      },
    })

    await renderOverviewPage()

    const productionHero = await screen.findByRole('region', { name: 'Produção e saúde da usina' })
    expect(within(productionHero).getByTestId('production-health-confidence-badge')).toHaveTextContent('Validar telemetria · ciclo 2026-07')

    const confidenceSection = await screen.findByRole('region', { name: 'Confiança dos dados do ciclo' })
    expect(within(confidenceSection).getByRole('complementary', { name: 'Confiança dos dados' })).toBeInTheDocument()
    expect(within(confidenceSection).getByText('Validar telemetria')).toBeInTheDocument()
    expect(within(confidenceSection).getByText('Decisão exige confirmação dos dados')).toBeInTheDocument()
  })

  it('autoconsumo/injetada/importada aparecem em um único componente de visualização (EnergyFlowDiagram)', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

    // O diagrama de fluxo é o único visual mantido — os outros dois visuais
    // redundantes (composição em barra e donut de origem do consumo) não
    // devem aparecer no módulo. O rótulo "Fluxo de energia" agora aparece uma
    // única vez, como `<h2>` da faixa de estado — `EnergyFlowDiagram` deixou
    // de ter sua própria sobrancelha duplicada (ver comentário no topo de
    // `EnergyFlowDiagram.tsx`).
    expect(await screen.findByRole('heading', { level: 2, name: 'Fluxo de energia — ciclo 2026-07' })).toBeInTheDocument()
    expect(screen.queryByText('Fluxo de energia no ciclo')).not.toBeInTheDocument()
    expect(screen.queryByText('Composição da produção')).not.toBeInTheDocument()
    expect(screen.queryByText('Origem do consumo')).not.toBeInTheDocument()
  })

  it('mostra autossuficiência e dependência da rede como dois números, sem uma terceira barra de composição', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

    const origem = await screen.findByRole('group', { name: 'Origem do consumo — ciclo 2026-07' })
    expect(within(origem).getByText('Autossuficiência')).toBeInTheDocument()
    expect(within(origem).getByText('77,7%')).toBeInTheDocument()
    expect(within(origem).getByText('Dependência da rede')).toBeInTheDocument()
    expect(within(origem).getByText('22,3%')).toBeInTheDocument()
    // A composição já está desenhada no fluxo; não há mais barra "Total 100%".
    expect(screen.queryByRole('img', { name: /Total 100%/ })).not.toBeInTheDocument()
  })

  // Migrado junto com a `StackedBar` para dentro da faixa de estado — o
  // fallback (2 `MetricCard` separados quando um dos dois indicadores vem
  // `null`, em vez de fabricar a barra com metade do dado ausente) precisa
  // continuar funcionando na nova localização exatamente como antes.
  it('mostra "—" (nunca 0% ou 100% fabricado) quando um dos dois percentuais vem null', async () => {
    vi.resetModules()
    const executiveWithNullGridDependency = {
      ...executivePayload,
      current_cycle: {
        ...executivePayload.current_cycle,
        indicators: {
          ...executivePayload.current_cycle.indicators,
          grid_dependency_rate_percent: null,
        },
      },
    }
    installApiMock({ executivePayload: executiveWithNullGridDependency })

    await renderOverviewPage()

    const origem = await screen.findByRole('group', { name: 'Origem do consumo — ciclo 2026-07' })
    expect(within(origem).getByText('77,7%')).toBeInTheDocument()
    expect(within(origem).getByText('—')).toBeInTheDocument()
    expect(within(origem).queryByText('0%')).not.toBeInTheDocument()
    expect(within(origem).queryByText('100%')).not.toBeInTheDocument()
  })

  it('não renderiza mais a seção "Energia e produção" (redundante com o diagrama de fluxo)', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

    await screen.findByRole('group', { name: 'Origem do consumo — ciclo 2026-07' })

    expect(screen.queryByText('Energia e produção')).not.toBeInTheDocument()
    // Os mesmos fatos continuam visíveis, só que uma única vez, no diagrama de fluxo.
    expect(screen.getByRole('heading', { level: 2, name: 'Fluxo de energia — ciclo 2026-07' })).toBeInTheDocument()
  })

  it('importada, injetada, autoconsumo e consumo aparecem em uma única visualização — nenhum card avulso duplica os rótulos de "Energia e produção" removidos', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

    await screen.findByRole('group', { name: 'Origem do consumo — ciclo 2026-07' })

    // `EnergyProductionSection` (removida da composição) usava exatamente
    // estes quatro rótulos em cards isolados — se algum deles reaparecer no
    // módulo fora do diagrama de fluxo, o fato voltou a ser duplicado.
    expect(screen.queryByText('Energia importada')).not.toBeInTheDocument()
    expect(screen.queryByText('Energia injetada')).not.toBeInTheDocument()
    expect(screen.queryByText('Autoconsumo estimado')).not.toBeInTheDocument()
    expect(screen.queryByText('Consumo total estimado')).not.toBeInTheDocument()

    // Os quatro fatos continuam visíveis, todos dentro do único diagrama de
    // fluxo — valores do payload: imported=120, injected=80,
    // self_consumption=420, total_consumption=540. Escopado pelo próprio SVG
    // do diagrama (aria-label começa com "Produção de") em vez de uma
    // sobrancelha de texto (removida, ver `EnergyFlowDiagram.tsx`) — sobe até
    // o `Card` mais próximo (`.rounded-2xl`, classe estável do componente
    // `Card`) para pegar o mesmo container de antes (SVG + tabela sr-only +
    // parágrafo de resumo).
    const flowSvg = screen.getByRole('img', { name: /^Produção de/ })
    const flowSection = flowSvg.closest('[data-testid="energy-flow-embedded"]') as HTMLElement
    expect(flowSection).not.toBeNull()
    // Barras de composição (ADR-077): valores na legenda, total no título.
    expect(flowSection).toHaveTextContent('Da rede120')
    expect(flowSection).toHaveTextContent('Injetada na rede80')
    expect(flowSection).toHaveTextContent('Consumida na casa420')
    expect(flowSection).toHaveTextContent('540 kWh')

    // E não aparecem duplicados fora dele, em nenhum outro card do módulo.
    const outsideFlow = document.body
    const allOccurrences = (pattern: RegExp) =>
      within(outsideFlow).queryAllByText(pattern).filter((el) => !flowSection.contains(el))
    expect(allOccurrences(/^120 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^80 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^420 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^540 kWh$/)).toHaveLength(0)
  })

  it('a seção de diagnósticos fica por último, em coluna única de leitura', async () => {
    vi.resetModules()
    installApiMock()

    const { container } = await renderOverviewPage()

    await screen.findByRole('group', { name: 'Origem do consumo — ciclo 2026-07' })

    const sections = Array.from(container.querySelectorAll('main > div.flex > section'))
    expect(sections.length).toBeGreaterThan(0)
    expect(sections[sections.length - 1]).toBe(container.querySelector('#diagnosticos'))
  })

  it('o resumo une estado da usina e fluxo de energia, em duas colunas que empilham fora de `lg`', async () => {
    vi.resetModules()
    installApiMock()

    const { container } = await renderOverviewPage()

    await screen.findByRole('heading', { level: 2, name: 'Fluxo de energia — ciclo 2026-07' })

    const band = container.querySelector('[data-testid="hero-band"]') as HTMLElement
    expect(band).not.toBeNull()
    // Duas colunas iguais só a partir de `lg`; abaixo empilha com o estado
    // primeiro (ordem de leitura igual no DOM e na tela).
    expect(band.className).toMatch(/\blg:grid-cols-\[minmax\(0,1fr\)_minmax\(0,1fr\)\]/)
    const [stateColumn, flowColumn] = Array.from(band.children) as HTMLElement[]
    expect(within(stateColumn).getByText(/Ciclo de referência/)).toBeInTheDocument()
    expect(within(flowColumn).getByRole('heading', { level: 2, name: 'Fluxo de energia — ciclo 2026-07' })).toBeInTheDocument()
    expect(within(flowColumn).getByRole('group', { name: 'Origem do consumo — ciclo 2026-07' })).toBeInTheDocument()

    // Os indicadores ficam FORA do resumo, logo abaixo dele.
    expect(within(band).queryByRole('group', { name: 'Resumo executivo do ciclo' })).not.toBeInTheDocument()
    const summary = screen.getByRole('group', { name: 'Resumo executivo do ciclo' })
    expect(summary).toHaveTextContent('500kWh')
    expect(summary).toHaveTextContent('40kWh')
    expect(summary).toHaveTextContent(/R\$\s*120,40/)
  })
})

describe('OverviewPage — erro global tem retry associado', () => {
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

    await renderOverviewPage()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Erro ao buscar dados/)

    const retryButton = screen.getByRole('button', { name: 'Tentar novamente' })
    fireEvent.click(retryButton)

    await screen.findByRole('group', { name: 'Origem do consumo — ciclo 2026-07' })
    expect(executiveCalls).toBe(2)
  })

  // Prova que os 2 recursos deste módulo (`executive`, `anomalies`) são
  // refeitos juntos (`refreshAll`), não só o que errou.
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

    await renderOverviewPage()

    await screen.findByRole('alert')
    await waitFor(() => {
      expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(1)
    })

    const retryButton = screen.getByRole('button', { name: 'Tentar novamente' })
    fireEvent.click(retryButton)

    await screen.findByRole('group', { name: 'Origem do consumo — ciclo 2026-07' })
    expect(executiveCalls).toBe(2)
    await waitFor(() => {
      expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(2)
    })
  })
})

describe('OverviewPage — âncora #diagnosticos (chip de atenção do HeroCard)', () => {
  it('o chip "N críticos" do HeroCard linka para #diagnosticos, que resolve para a <section id="diagnosticos"> real deste módulo', async () => {
    vi.resetModules()
    // Payload com pelo menos 1 diagnóstico CRITICAL, para o chip
    // (`AttentionSummary`) ser renderizado — `executivePayload` default tem
    // `diagnostics: []`.
    const executiveWithCriticalDiagnostic = {
      ...executivePayload,
      current_cycle: {
        ...executivePayload.current_cycle,
        diagnostics: [
          {
            code: 'LOW_SELF_SUFFICIENCY',
            severity: 'CRITICAL',
            message: 'Autossuficiência abaixo do esperado.',
            recommended_action: 'Revisar consumo importado.',
          },
        ],
      },
    }
    installApiMock({ executivePayload: executiveWithCriticalDiagnostic })

    const { container } = await renderOverviewPage()

    const chip = await screen.findByRole('link', { name: /crítico.*ver diagnósticos/i })
    expect(chip).toHaveAttribute('href', '#diagnosticos')

    const target = container.querySelector('#diagnosticos')
    expect(target).not.toBeNull()
    expect(target?.tagName.toLowerCase()).toBe('section')
  })
})
