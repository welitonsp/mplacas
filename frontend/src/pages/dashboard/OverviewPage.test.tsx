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

    await screen.findByText('Origem do consumo — ciclo 2026-07')
    await waitFor(() => {
      expect(fetchExecutiveMock).toHaveBeenCalledTimes(1)
      expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(1)
    })
    expect(fetchExecutiveMock).toHaveBeenCalledWith(singlePlant.id)
    expect(fetchAnomalyHistoryMock).toHaveBeenCalledWith(singlePlant.id)
  })

  it('abre a Visão Geral com confiança dos dados antes da decisão executiva e do cockpit visual', async () => {
    vi.resetModules()
    installApiMock()

    const { container } = await renderOverviewPage()

    const confidenceSection = await screen.findByRole('region', { name: 'Confiança dos dados do ciclo' })
    expect(within(confidenceSection).getByRole('complementary', { name: 'Confiança dos dados' })).toBeInTheDocument()
    expect(within(confidenceSection).getByText('Alta confiança')).toBeInTheDocument()
    expect(within(confidenceSection).getByText('Dados prontos para decisão')).toBeInTheDocument()

    const decisionSection = await screen.findByRole('region', { name: 'Decisão executiva do ciclo' })
    expect(within(decisionSection).getByRole('heading', { level: 2, name: 'Ciclo pede acompanhamento' })).toBeInTheDocument()
    expect(within(decisionSection).getByText('Acompanhar hoje')).toBeInTheDocument()
    expect(within(decisionSection).getByText('Próxima ação')).toBeInTheDocument()
    expect(within(decisionSection).getByRole('group', { name: 'Sinais usados na decisão' })).toBeInTheDocument()

    const sections = Array.from(container.querySelectorAll('main > div.grid > section'))
    expect(sections[0]).toBe(confidenceSection)
    expect(sections[1]).toBe(decisionSection)
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

  it('unifica autossuficiência e dependência da rede em uma única StackedBar de 2 segmentos somando 100%', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

    await screen.findByText('Origem do consumo — ciclo 2026-07')

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

  // Migrado junto com a `StackedBar` para dentro da faixa de estado — o
  // fallback (2 `MetricCard` separados quando um dos dois indicadores vem
  // `null`, em vez de fabricar a barra com metade do dado ausente) precisa
  // continuar funcionando na nova localização exatamente como antes.
  it('mantém o fallback de dois MetricCard (em vez da StackedBar) quando um dos dois indicadores vem null, agora dentro da faixa de estado', async () => {
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

    const { container } = await renderOverviewPage()

    await screen.findByText('Autossuficiência')

    // Sem os dois valores, a StackedBar (e seu rótulo de seção) não aparece.
    expect(screen.queryByRole('img', { name: /Total 100%/ })).not.toBeInTheDocument()
    expect(screen.queryByText('Origem do consumo — ciclo 2026-07')).not.toBeInTheDocument()

    // Os dois `MetricCard` aparecem no lugar, dentro da coluna de fluxo da
    // faixa — o valor disponível continua visível com sua barra de progresso,
    // e o valor ausente mostra "—" em vez de esconder o card inteiro. Valor e
    // unidade são checados separadamente (não como string combinada "77,7%")
    // porque `MetricCard` os renderiza em nós de texto distintos (valor +
    // `<span>` de unidade) — mesmo padrão já usado por `MetricCard.test.tsx`.
    const band = container.querySelector('[data-testid="hero-band"]') as HTMLElement
    expect(band).not.toBeNull()
    expect(within(band).getByText('Autossuficiência')).toBeInTheDocument()
    expect(within(band).getByText('Dependência da rede')).toBeInTheDocument()
    expect(within(band).getByText(/77,7/)).toBeInTheDocument()
    expect(within(band).getAllByText('%').length).toBeGreaterThan(0)
    expect(within(band).getByText('—')).toBeInTheDocument()
    expect(within(band).getByRole('progressbar', { name: 'Autossuficiência' })).toBeInTheDocument()
    expect(within(band).queryByRole('progressbar', { name: 'Dependência da rede' })).not.toBeInTheDocument()
  })

  it('não renderiza mais a seção "Energia e produção" (redundante com o diagrama de fluxo)', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

    await screen.findByText('Origem do consumo — ciclo 2026-07')

    expect(screen.queryByText('Energia e produção')).not.toBeInTheDocument()
    // Os mesmos fatos continuam visíveis, só que uma única vez, no diagrama de fluxo.
    expect(screen.getByRole('heading', { level: 2, name: 'Fluxo de energia — ciclo 2026-07' })).toBeInTheDocument()
  })

  it('importada, injetada, autoconsumo e consumo aparecem em uma única visualização — nenhum card avulso duplica os rótulos de "Energia e produção" removidos', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

    await screen.findByText('Origem do consumo — ciclo 2026-07')

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
    const flowSection = flowSvg.closest('.rounded-2xl') as HTMLElement
    expect(flowSection).not.toBeNull()
    expect(within(flowSection).getAllByText(/120 kWh/).length).toBeGreaterThan(0)
    expect(within(flowSection).getAllByText(/80 kWh/).length).toBeGreaterThan(0)
    expect(within(flowSection).getAllByText(/420 kWh/).length).toBeGreaterThan(0)
    expect(within(flowSection).getAllByText(/540 kWh/).length).toBeGreaterThan(0)

    // E não aparecem duplicados fora dele, em nenhum outro card do módulo.
    const outsideFlow = document.body
    const allOccurrences = (pattern: RegExp) =>
      within(outsideFlow).getAllByText(pattern).filter((el) => !flowSection.contains(el))
    expect(allOccurrences(/^120 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^80 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^420 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^540 kWh$/)).toHaveLength(0)
  })

  it('a seção de diagnósticos ocupa a linha inteira abaixo do cockpit, sem deixar uma coluna vazia', async () => {
    vi.resetModules()
    installApiMock()

    const { container } = await renderOverviewPage()

    await screen.findByText('Origem do consumo — ciclo 2026-07')

    // O cockpit e a área de atenção usam a linha inteira. A comparação com o
    // ciclo anterior, quando existe, é organizada dentro da própria seção.
    const sections = Array.from(container.querySelectorAll('main > div.grid > section'))
    expect(sections.length).toBeGreaterThan(0)

    const nonFullWidthAtMd = sections.filter((section) => {
      const match = section.className.match(/\bmd:col-span-(\d+)\b/)
      return match !== null && match[1] !== '6'
    })
    expect(nonFullWidthAtMd).toHaveLength(0)
    expect(container.querySelector('#diagnosticos')).toHaveClass('md:col-span-6', 'lg:col-span-12')
  })

  it('a faixa de estado une HeroCard e EnergyFlowDiagram numa superfície com fundo de marca, em duas colunas (~5/12 e ~7/12) que empilham fora de `lg`', async () => {
    vi.resetModules()
    installApiMock()

    const { container } = await renderOverviewPage()

    await screen.findByRole('heading', { level: 2, name: 'Fluxo de energia — ciclo 2026-07' })

    const band = container.querySelector('[data-testid="hero-band"]') as HTMLElement
    expect(band).not.toBeNull()
    // Superfície de ESTRUTURA (nunca codifica severidade de dado — isso
    // continua vindo só de `SEVERITY_*`/`accent` dentro dela), full-width no
    // grid de topo (`md:col-span-6 lg:col-span-12`), mesmo token dos dois
    // temas (ADR-071), cantos generosos e padding maior que o `Card` padrão.
    expect(band.className).toMatch(/\bmd:col-span-6\b/)
    expect(band.className).toMatch(/\blg:col-span-12\b/)
    expect(band.className).toMatch(/bg-\[var\(--color-brand-primary-light\)\]/)
    expect(band.className).toMatch(/\brounded-3xl\b/)

    // Dentro da faixa: HeroCard à esquerda (~5/12), fluxo à direita (~7/12),
    // só a partir de `lg` — abaixo disso empilha (Hero primeiro, fluxo
    // depois), ordem de leitura preservada tanto no DOM quanto no layout
    // empilhado.
    const innerGrid = band.querySelector(':scope > div.grid') as HTMLElement
    expect(innerGrid).not.toBeNull()
    const [stateColumn, flowColumn] = Array.from(innerGrid.children) as HTMLElement[]
    expect(stateColumn.className).toMatch(/\blg:col-span-5\b/)
    expect(flowColumn.className).toMatch(/\blg:col-span-7\b/)
    expect(within(stateColumn).getByText(/Ciclo de referência/)).toBeInTheDocument()
    expect(within(flowColumn).getByRole('heading', { level: 2, name: 'Fluxo de energia — ciclo 2026-07' })).toBeInTheDocument()

    // A StackedBar de indicadores percentuais é a tira sob o diagrama —
    // continua dentro da mesma coluna do fluxo, não numa seção à parte.
    expect(within(flowColumn).getByText('Origem do consumo — ciclo 2026-07')).toBeInTheDocument()
    expect(within(flowColumn).getByRole('img', { name: /Total 100%/ })).toBeInTheDocument()

    const summary = within(band).getByRole('group', { name: 'Resumo executivo do ciclo' })
    expect(within(summary).getByText('500 kWh')).toBeInTheDocument()
    expect(within(summary).getByText('40 kWh')).toBeInTheDocument()
    expect(within(summary).getByText(/R\$\s*120,40/)).toBeInTheDocument()
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

    await screen.findByText('Origem do consumo — ciclo 2026-07')
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

    await screen.findByText('Origem do consumo — ciclo 2026-07')
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
