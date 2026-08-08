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

    await screen.findByText('Indicadores percentuais')
    await waitFor(() => {
      expect(fetchExecutiveMock).toHaveBeenCalledTimes(1)
      expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(1)
    })
    expect(fetchExecutiveMock).toHaveBeenCalledWith(singlePlant.id)
    expect(fetchAnomalyHistoryMock).toHaveBeenCalledWith(singlePlant.id)
  })

  it('autoconsumo/injetada/importada aparecem em um único componente de visualização (EnergyFlowDiagram)', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

    // O diagrama de fluxo é o único visual mantido — os outros dois visuais
    // redundantes (composição em barra e donut de origem do consumo) não
    // devem aparecer no módulo.
    expect(await screen.findByText('Fluxo de energia no ciclo')).toBeInTheDocument()
    expect(screen.queryByText('Composição da produção')).not.toBeInTheDocument()
    expect(screen.queryByText('Origem do consumo')).not.toBeInTheDocument()
  })

  it('unifica autossuficiência e dependência da rede em uma única StackedBar de 2 segmentos somando 100%', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

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

  it('não renderiza mais a seção "Energia e produção" (redundante com o diagrama de fluxo)', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

    await screen.findByText('Indicadores percentuais')

    expect(screen.queryByText('Energia e produção')).not.toBeInTheDocument()
    // Os mesmos fatos continuam visíveis, só que uma única vez, no diagrama de fluxo.
    expect(screen.getByText('Fluxo de energia no ciclo')).toBeInTheDocument()
  })

  it('importada, injetada, autoconsumo e consumo aparecem em uma única visualização — nenhum card avulso duplica os rótulos de "Energia e produção" removidos', async () => {
    vi.resetModules()
    installApiMock()

    await renderOverviewPage()

    await screen.findByText('Indicadores percentuais')

    // `EnergyProductionSection` (removida da composição) usava exatamente
    // estes quatro rótulos em cards isolados — se algum deles reaparecer no
    // módulo fora do diagrama de fluxo, o fato voltou a ser duplicado.
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

    // E não aparecem duplicados fora dele, em nenhum outro card do módulo.
    const outsideFlow = document.body
    const allOccurrences = (pattern: RegExp) =>
      within(outsideFlow).getAllByText(pattern).filter((el) => !flowSection.contains(el))
    expect(allOccurrences(/^120 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^80 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^420 kWh$/)).toHaveLength(0)
    expect(allOccurrences(/^540 kWh$/)).toHaveLength(0)
  })

  it('pelo menos duas seções distintas declaram md:col-span diferente de 6 (grid de 6 colunas)', async () => {
    vi.resetModules()
    installApiMock()

    const { container } = await renderOverviewPage()

    await screen.findByText('Indicadores percentuais')

    const sections = Array.from(container.querySelectorAll('main > div.grid > section'))
    expect(sections.length).toBeGreaterThan(0)

    const nonFullWidthAtMd = sections.filter((section) => {
      const match = section.className.match(/\bmd:col-span-(\d+)\b/)
      return match !== null && match[1] !== '6'
    })

    // O grid do módulo é `md:grid-cols-6` — uma seção com `md:col-span-6` (ou
    // sem span declarado) ocupa a largura inteira, igual ao empilhamento de
    // mobile. Pelo menos duas seções precisam declarar um span menor no
    // breakpoint `md` para o tablet deixar de ser uma coluna única.
    expect(nonFullWidthAtMd.length).toBeGreaterThanOrEqual(2)
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

    await screen.findByText('Indicadores percentuais')
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

    await screen.findByText('Indicadores percentuais')
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
