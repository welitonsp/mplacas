import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import {
  anomalyPayload,
  fallbackPhotovoltaicSummaryPayload,
  jsonResponse,
  monthlyHistoryPayload,
  photovoltaicSummaryPayload,
  singlePlant,
} from '../../test/dashboardFixtures'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste (ver `LoginPage.test.tsx`,
// `DashboardPage.test.tsx`, `FinancialPage.test.tsx`, `TechnicalPage.test.tsx`).
vi.mock('../../env', () => ({
  API_URL: 'https://api.example.test',
}))

// `ProductionPage` (e, transitivamente, `PlantProvider`/`AuthProvider` usados
// por `renderModule`) depende de 4 exports de `../../lib/api`: os três
// recursos do módulo (`fetchAnomalyHistory`, `fetchPhotovoltaicSummary`,
// `fetchMonthlyProductionHistory`), mais `fetchPlants` (`PlantContext`) e
// `configureApi` (`AuthContext`). Nenhum dos outros fetchers de
// `../../lib/api` (`fetchExecutiveDashboard`, `fetchFinancialReturn`) é
// importado por este módulo — se algum teste abaixo os disparasse, o mock
// (que não os declara) já provaria a fronteira de fetch por módulo (ADR-072,
// Decisão 3).
interface ApiMockOverrides {
  fetchAnomalyHistory?: (plantId: string, days?: number) => Promise<Response>
  fetchPhotovoltaicSummary?: (plantId: string) => Promise<Response>
  fetchMonthlyProductionHistory?: (plantId: string, limit?: number) => Promise<Response>
  fetchPlants?: () => Promise<unknown[]>
}

function installApiMock(overrides: ApiMockOverrides = {}) {
  vi.doMock('../../lib/api', () => ({
    fetchAnomalyHistory:
      overrides.fetchAnomalyHistory ?? vi.fn(async () => jsonResponse(anomalyPayload)),
    fetchPhotovoltaicSummary:
      overrides.fetchPhotovoltaicSummary ?? vi.fn(async () => jsonResponse(photovoltaicSummaryPayload)),
    fetchMonthlyProductionHistory:
      overrides.fetchMonthlyProductionHistory ?? vi.fn(async () => jsonResponse(monthlyHistoryPayload)),
    fetchPlants: overrides.fetchPlants ?? vi.fn(async () => [singlePlant]),
    configureApi: vi.fn(),
  }))
}

async function renderProductionPage() {
  const { ProductionPage } = await import('./ProductionPage')
  const { renderModule } = await import('../../test/renderModule')
  const { DASHBOARD_PRODUCTION_PATH } = await import('../../routes')
  return renderModule(<ProductionPage />, DASHBOARD_PRODUCTION_PATH)
}

describe('ProductionPage — módulo Produção (ADR-072, Etapa 4)', () => {
  it('dispara exatamente 3 requisições de dados — /energy/anomalies/latest, /photovoltaic/summary e /reports/monthly/history, nenhuma outra', async () => {
    vi.resetModules()
    const fetchAnomalyHistoryMock = vi.fn(async () => jsonResponse(anomalyPayload))
    const fetchPhotovoltaicSummaryMock = vi.fn(async () => jsonResponse(photovoltaicSummaryPayload))
    const fetchMonthlyProductionHistoryMock = vi.fn(async () => jsonResponse(monthlyHistoryPayload))
    installApiMock({
      fetchAnomalyHistory: fetchAnomalyHistoryMock,
      fetchPhotovoltaicSummary: fetchPhotovoltaicSummaryMock,
      fetchMonthlyProductionHistory: fetchMonthlyProductionHistoryMock,
    })

    await renderProductionPage()

    // `data-testid="column-series-visual"` (ver `charts/ColumnSeries.tsx`)
    // identifica a parte visual do gráfico sem ambiguidade com a tabela
    // `sr-only` que repete os mesmos rótulos/valores de propósito.
    await screen.findByTestId('column-series-visual')
    await waitFor(() => {
      expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(1)
      expect(fetchPhotovoltaicSummaryMock).toHaveBeenCalledTimes(1)
      expect(fetchMonthlyProductionHistoryMock).toHaveBeenCalledTimes(1)
    })
    expect(fetchAnomalyHistoryMock).toHaveBeenCalledWith(singlePlant.id)
    expect(fetchPhotovoltaicSummaryMock).toHaveBeenCalledWith(singlePlant.id)
    expect(fetchMonthlyProductionHistoryMock).toHaveBeenCalledWith(singlePlant.id, 12)
  })
})

describe('ProductionPage — resumo operacional', () => {
  it('destaca produção real, esperado, desvio e sequência de atenção no topo', async () => {
    vi.resetModules()
    installApiMock()

    await renderProductionPage()

    const title = await screen.findByRole('heading', { level: 2, name: 'Resumo operacional' })
    const section = title.closest('section') as HTMLElement

    expect(within(section).getByText('Última produção')).toBeInTheDocument()
    await waitFor(() => {
      expect(within(section).getByText('40 kWh')).toBeInTheDocument()
    })
    expect(within(section).getByText('Dado de 30/07/2026')).toBeInTheDocument()
    expect(within(section).getByText('Esperado no dia')).toBeInTheDocument()
    expect(within(section).getByText('44 kWh')).toBeInTheDocument()
    expect(within(section).getByText('Desvio')).toBeInTheDocument()
    expect(within(section).getByText('-9%')).toBeInTheDocument()
    expect(within(section).getByText('Sequência de atenção')).toBeInTheDocument()
    expect(within(section).getByText('2 dias')).toBeInTheDocument()
    expect(within(section).getByText('abaixo do esperado')).toBeInTheDocument()
  })

  it('mostra diagnóstico de produção com pior dia, perda estimada e próxima ação antes dos gráficos', async () => {
    vi.resetModules()
    installApiMock()

    const { container } = await renderProductionPage()

    const diagnosisSection = await screen.findByRole('region', { name: 'Diagnóstico de produção do período' })
    await waitFor(() => {
      expect(within(diagnosisSection).getByRole('heading', { level: 2, name: 'Diagnóstico: perda recorrente de produção' })).toBeInTheDocument()
    })
    expect(within(diagnosisSection).getByText(/2 dias seguidos abaixo do esperado/)).toBeInTheDocument()
    expect(within(diagnosisSection).getByText(/Perda estimada de 10 kWh/)).toBeInTheDocument()
    expect(within(diagnosisSection).getByRole('group', { name: 'Sinais do diagnóstico de produção' })).toBeInTheDocument()

    const chart = await screen.findByTestId('column-series-visual')
    const chartSection = chart.closest('section') as HTMLElement
    expect(container.contains(diagnosisSection)).toBe(true)
    expect(chartSection).not.toBeNull()
    expect(Boolean(diagnosisSection.compareDocumentPosition(chartSection) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
  })
})

describe('ProductionPage — seção "Produção por ciclo de faturamento"', () => {
  it('renderiza as colunas do histórico de ciclos, não o banner de erro', async () => {
    vi.resetModules()
    installApiMock()

    await renderProductionPage()

    const sectionTitle = await screen.findByText('Produção por ciclo de faturamento')
    const section = sectionTitle.closest('section') as HTMLElement

    await waitFor(() => {
      expect(within(section).queryByRole('alert')).not.toBeInTheDocument()
    })

    // Os 3 ciclos de `monthlyHistoryPayload` (default de `installApiMock`)
    // aparecem como colunas reais (`ColumnSeries`, um único `role="img"` para
    // toda a série — ver `charts/ColumnSeries.tsx`), em ordem cronológica,
    // com o valor formatado. Escopado à parte visual (`data-testid`) porque
    // os mesmos rótulos/valores se repetem, de propósito, na tabela
    // `sr-only` da primitiva — sem esse escopo `getByText` ficaria ambíguo.
    await waitFor(() => {
      expect(within(section).getByRole('img')).toBeInTheDocument()
    })
    const visual = within(within(section).getByTestId('column-series-visual'))
    expect(visual.getByText('mar/26')).toBeInTheDocument()
    expect(visual.getByText('abr/26')).toBeInTheDocument()
    expect(visual.getByText('mai/26')).toBeInTheDocument()
    expect(visual.getByText('980 kWh')).toBeInTheDocument()
    // "1.050 kWh" aparece duas vezes dentro da parte visual: o valor da
    // coluna abr/26 E o tique do topo do eixo Y, já que abr/26 é o maior
    // valor da série (mesma coincidência tratada em `ColumnSeries.test.tsx`).
    expect(visual.getAllByText('1.050 kWh')).toHaveLength(2)
    expect(visual.getByText('500 kWh')).toBeInTheDocument()

    // mai/26 tem missing_days: 3 no payload — único ciclo com o selo de
    // dados parciais.
    expect(within(section).getAllByText('dados parciais')).toHaveLength(1)
  })

  it('mostra o esqueleto de carregamento enquanto /reports/monthly/history está em voo, depois as colunas reais (sucesso)', async () => {
    vi.resetModules()
    let resolveFetch: (value: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve
    })
    installApiMock({ fetchMonthlyProductionHistory: vi.fn(async () => pending) })

    await renderProductionPage()

    const sectionTitle = await screen.findByText('Produção por ciclo de faturamento')
    const section = sectionTitle.closest('section') as HTMLElement
    expect(within(section).queryByRole('img')).not.toBeInTheDocument()

    resolveFetch(jsonResponse(monthlyHistoryPayload))

    await waitFor(() => {
      expect(within(section).getByRole('img')).toBeInTheDocument()
    })
    expect(
      within(within(section).getByTestId('column-series-visual')).getByText('mar/26')
    ).toBeInTheDocument()
  })

  it('mostra RetryableError (não as colunas) quando fetchMonthlyProductionHistory falha, sem travar o resto do módulo, e refaz o fetch ao clicar em "Tentar novamente"', async () => {
    vi.resetModules()
    const fetchMonthlyProductionHistoryMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: 'boom' }, 500))
      .mockResolvedValueOnce(jsonResponse(monthlyHistoryPayload))
    installApiMock({ fetchMonthlyProductionHistory: fetchMonthlyProductionHistoryMock })

    await renderProductionPage()

    const sectionTitle = await screen.findByText('Produção por ciclo de faturamento')
    const section = sectionTitle.closest('section') as HTMLElement

    await waitFor(() => {
      expect(within(section).getByRole('alert')).toBeInTheDocument()
    })
    // Mensagem fixa vinda de `usePlantResource` — sem sufixo de status HTTP:
    // o detalhe técnico vai para o console, nunca para a tela (mesma política
    // de `ErrorBoundary.tsx`).
    expect(within(section).getByRole('alert')).toHaveTextContent(
      'Erro ao buscar histórico de produção.'
    )

    // O erro isolado desta seção não trava o restante do módulo.
    expect(await screen.findByText('Histórico de produção')).toBeInTheDocument()

    fireEvent.click(within(section).getByRole('button', { name: 'Tentar novamente' }))

    await waitFor(() => {
      expect(within(section).getByRole('img')).toBeInTheDocument()
    })
    expect(fetchMonthlyProductionHistoryMock).toHaveBeenCalledTimes(2)
  })
})

describe('ProductionPage — "Histórico de produção" e "Produção do último dia vs. esperada"', () => {
  it('mostra o esqueleto de carregamento enquanto /energy/anomalies/latest está em voo, depois o conteúdo real (sucesso)', async () => {
    vi.resetModules()
    let resolveFetch: (value: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve
    })
    installApiMock({ fetchAnomalyHistory: vi.fn(async () => pending) })

    await renderProductionPage()

    const historyTitle = await screen.findByText('Histórico de produção')
    const historySection = historyTitle.closest('section') as HTMLElement
    expect(historySection.querySelector('.animate-pulse')).toBeInTheDocument()

    const latestTitle = await screen.findByText('Produção do último dia vs. esperada')
    const latestSection = latestTitle.closest('section') as HTMLElement
    expect(latestSection.querySelector('.animate-pulse')).toBeInTheDocument()

    resolveFetch(jsonResponse(anomalyPayload))

    // `anomalyPayload.daily` traz dois dias; o mais recente (2026-07-30) tem
    // actual_production_kwh=40 e expected_production_kwh=44 — mesma escala
    // diária.
    await waitFor(() => {
      expect(within(latestSection).getByText('40 kWh')).toBeInTheDocument()
    })
    expect(within(latestSection).getByText(/esperado 44 kWh/)).toBeInTheDocument()
    await waitFor(() => {
      expect(within(historySection).getByRole('slider')).toBeInTheDocument()
    })
  })

  it('mostra RetryableError no histórico de produção quando /energy/anomalies/latest responde 500, e refaz o fetch ao clicar em "Tentar novamente"', async () => {
    vi.resetModules()
    const fetchAnomalyHistoryMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: 'boom' }, 500))
      .mockResolvedValueOnce(jsonResponse(anomalyPayload))
    installApiMock({ fetchAnomalyHistory: fetchAnomalyHistoryMock })

    await renderProductionPage()

    const historyTitle = await screen.findByText('Histórico de produção')
    const historySection = historyTitle.closest('section') as HTMLElement

    await waitFor(() => {
      expect(within(historySection).getByText(
        'Não foi possível carregar o histórico de produção diária. Tente novamente.'
      )).toBeInTheDocument()
    })

    // A produção do último dia também reflete a ausência de dado (mesmo
    // recurso `anomalies`), sem card de erro próprio — estado indisponível
    // explícito, não um alerta duplicado. `getByRole('heading', ...)` evita
    // ambiguidade: o texto se repete (título da seção + fallback interno do
    // `LatestDailyProductionCard`, que reusa o mesmo rótulo).
    const latestTitle = screen.getByRole('heading', { level: 2, name: 'Produção do último dia vs. esperada' })
    const latestSection = latestTitle.closest('section') as HTMLElement
    expect(
      within(latestSection).getByText(
        'Ainda não há produção diária registrada para comparar com o esperado.'
      )
    ).toBeInTheDocument()

    fireEvent.click(within(historySection).getByRole('button', { name: 'Tentar novamente' }))

    await waitFor(() => {
      expect(within(historySection).getByRole('slider')).toBeInTheDocument()
    })
    expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(2)
  })
})

describe('ProductionPage — histórico de produção não depende mais do baseline sazonal (contrato 200 sempre)', () => {
  it('busca /energy/anomalies/latest assim que há plantId, sem esperar expectedProduction.available e sem parâmetros extras (ex.: o antigo expected_daily_production_kwh)', async () => {
    vi.resetModules()
    const fetchAnomalyHistoryMock = vi.fn(async () => jsonResponse(anomalyPayload))

    installApiMock({
      fetchAnomalyHistory: fetchAnomalyHistoryMock,
      // `/photovoltaic/summary` responde SEM baseline (usina nova) — a busca
      // de anomalias não pode esperar por esse resultado.
      fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(fallbackPhotovoltaicSummaryPayload)),
    })

    await renderProductionPage()

    await waitFor(() => {
      expect(fetchAnomalyHistoryMock).toHaveBeenCalled()
    })
    // O módulo chama só com `plantId` — nenhum segundo argumento (como o
    // antigo `expected_daily_production_kwh`) é passado; `days` fica a cargo
    // do default de `fetchAnomalyHistory` em `lib/api.ts`.
    expect(fetchAnomalyHistoryMock).toHaveBeenCalledWith(singlePlant.id)
  })

  it('mostra o gráfico de histórico com produção real, sem linha "Esperado" e sem cair no fallback de dados insuficientes, quando a usina tem produção real mas não tem baseline sazonal', async () => {
    vi.resetModules()

    const noBaselineAnomalyPayload = {
      plant_id: 'plant-1',
      days_analyzed: 1,
      current_streak_days: 0,
      worst_level: null,
      expected_unavailable_reason: 'REFERENCE_YEAR_INCOMPLETE',
      daily: [
        {
          date: '2026-07-30',
          actual_production_kwh: 40,
          expected_production_kwh: null,
          level: null,
          deviation_percent: null,
          irradiation_kwh_m2: null,
        },
      ],
    }

    installApiMock({
      fetchAnomalyHistory: vi.fn(async () => jsonResponse(noBaselineAnomalyPayload)),
      fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(fallbackPhotovoltaicSummaryPayload)),
    })

    await renderProductionPage()

    const sectionTitle = await screen.findByText('Histórico de produção')
    const section = sectionTitle.closest('section') as HTMLElement

    await waitFor(() => {
      expect(within(section).getByRole('slider')).toBeInTheDocument()
    })
    expect(within(section).getAllByText('40 kWh').length).toBeGreaterThanOrEqual(1)
    expect(within(section).queryByText('Esperado')).not.toBeInTheDocument()
    expect(within(section).queryByText(/histórico de desempenho insuficiente/)).not.toBeInTheDocument()
    expect(within(section).queryByText(/primeiro ano de referência/)).not.toBeInTheDocument()
  })
})

describe('ProductionPage — re-busca dados quando a usina ativa muda (ADR-069, Etapa C)', () => {
  it('refaz as 3 chamadas de dados com o novo plant_id quando o PlantContext resolve outra usina', async () => {
    vi.resetModules()

    const secondPlant = {
      id: '00000000-0000-0000-0000-000000000002',
      name: 'Segunda usina',
      installedPowerKwp: null,
    }
    const anomalyCallsPlantIds: string[] = []
    const pvSummaryCallsPlantIds: string[] = []
    const monthlyHistoryCallsPlantIds: string[] = []

    installApiMock({
      fetchAnomalyHistory: vi.fn(async (plantId: string) => {
        anomalyCallsPlantIds.push(plantId)
        return jsonResponse(anomalyPayload)
      }),
      fetchPhotovoltaicSummary: vi.fn(async (plantId: string) => {
        pvSummaryCallsPlantIds.push(plantId)
        return jsonResponse(photovoltaicSummaryPayload)
      }),
      fetchMonthlyProductionHistory: vi.fn(async (plantId: string) => {
        monthlyHistoryCallsPlantIds.push(plantId)
        return jsonResponse(monthlyHistoryPayload)
      }),
      fetchPlants: vi.fn(async () => [singlePlant, secondPlant]),
    })

    const { ProductionPage } = await import('./ProductionPage')
    const { render } = await import('@testing-library/react')
    const { MemoryRouter } = await import('react-router')
    const { AuthProvider } = await import('../../contexts/AuthContext')
    const { PlantProvider, usePlant } = await import('../../contexts/PlantContext')
    const { DASHBOARD_PRODUCTION_PATH } = await import('../../routes')

    function PlantSwitcher() {
      const { selectPlant } = usePlant()
      return <button onClick={() => selectPlant(secondPlant.id)}>trocar-usina</button>
    }

    render(
      <MemoryRouter initialEntries={[DASHBOARD_PRODUCTION_PATH]}>
        <AuthProvider>
          <PlantProvider>
            <PlantSwitcher />
            <main>
              <ProductionPage />
            </main>
          </PlantProvider>
        </AuthProvider>
      </MemoryRouter>
    )

    await screen.findByTestId('column-series-visual')
    expect(anomalyCallsPlantIds).toEqual([singlePlant.id])
    expect(pvSummaryCallsPlantIds).toEqual([singlePlant.id])
    expect(monthlyHistoryCallsPlantIds).toEqual([singlePlant.id])

    screen.getByRole('button', { name: 'trocar-usina' }).click()

    await waitFor(() => {
      expect(anomalyCallsPlantIds).toEqual([singlePlant.id, secondPlant.id])
      expect(pvSummaryCallsPlantIds).toEqual([singlePlant.id, secondPlant.id])
      expect(monthlyHistoryCallsPlantIds).toEqual([singlePlant.id, secondPlant.id])
    })
  })
})
