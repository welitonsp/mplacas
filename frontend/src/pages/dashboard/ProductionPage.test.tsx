import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import {
  anomalyPayload,
  executivePayload,
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

// `ProductionPage` (aba Energia, ADR-083 — e, transitivamente,
// `PlantProvider`/`AuthProvider` usados por `renderModule`) depende de 6
// exports de `../../lib/api`: os quatro recursos do módulo
// (`fetchExecutiveDashboard`, para "para onde foi a energia",
// `fetchAnomalyHistory`, `fetchPhotovoltaicSummary`,
// `fetchMonthlyProductionHistory`), mais `fetchPlants` (`PlantContext`) e
// `configureApi` (`AuthContext`). `fetchFinancialReturn` não é importado por
// este módulo — se algum teste o disparasse, o mock (que não o declara) já
// provaria a fronteira de fetch por módulo (ADR-072, Decisão 3).
interface ApiMockOverrides {
  fetchExecutiveDashboard?: (plantId: string) => Promise<Response>
  fetchAnomalyHistory?: (plantId: string, days?: number) => Promise<Response>
  fetchPhotovoltaicSummary?: (plantId: string) => Promise<Response>
  fetchMonthlyProductionHistory?: (plantId: string, limit?: number) => Promise<Response>
  fetchPlants?: () => Promise<unknown[]>
}

function installApiMock(overrides: ApiMockOverrides = {}) {
  vi.doMock('../../lib/api', () => ({
    fetchExecutiveDashboard:
      overrides.fetchExecutiveDashboard ?? vi.fn(async () => jsonResponse(executivePayload)),
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
  it('dispara exatamente 4 requisições de dados — /energy/executive/latest, /energy/anomalies/latest, /photovoltaic/summary e /reports/monthly/history, nenhuma outra', async () => {
    vi.resetModules()
    const fetchExecutiveDashboardMock = vi.fn(async () => jsonResponse(executivePayload))
    const fetchAnomalyHistoryMock = vi.fn(async () => jsonResponse(anomalyPayload))
    const fetchPhotovoltaicSummaryMock = vi.fn(async () => jsonResponse(photovoltaicSummaryPayload))
    const fetchMonthlyProductionHistoryMock = vi.fn(async () => jsonResponse(monthlyHistoryPayload))
    installApiMock({
      fetchExecutiveDashboard: fetchExecutiveDashboardMock,
      fetchAnomalyHistory: fetchAnomalyHistoryMock,
      fetchPhotovoltaicSummary: fetchPhotovoltaicSummaryMock,
      fetchMonthlyProductionHistory: fetchMonthlyProductionHistoryMock,
    })

    await renderProductionPage()

    // O ciclo mais recente da comparação placas × Equatorial já renderizado.
    await screen.findByRole('heading', { level: 3, name: /mai\/26/ })
    await waitFor(() => {
      expect(fetchExecutiveDashboardMock).toHaveBeenCalledTimes(1)
      expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(1)
      expect(fetchPhotovoltaicSummaryMock).toHaveBeenCalledTimes(1)
      expect(fetchMonthlyProductionHistoryMock).toHaveBeenCalledTimes(1)
    })
    expect(fetchAnomalyHistoryMock).toHaveBeenCalledWith(singlePlant.id)
    expect(fetchPhotovoltaicSummaryMock).toHaveBeenCalledWith(singlePlant.id)
    expect(fetchMonthlyProductionHistoryMock).toHaveBeenCalledWith(singlePlant.id, 12)
  })
})

describe('ProductionPage — comparação com o esperado (ADR-083, etapa 3)', () => {
  it('com referência: "Último dia contra o esperado" mostra régua, desvio e sequência, sem aviso de referência', async () => {
    vi.resetModules()
    installApiMock()

    await renderProductionPage()

    const title = await screen.findByRole('heading', { level: 2, name: 'Último dia contra o esperado' })
    const section = title.closest('section') as HTMLElement
    await waitFor(() => {
      expect(within(section).getByText('Produção de 30/07/2026 vs. esperada')).toBeInTheDocument()
    })
    expect(within(section).getByText(/esperado 44 kWh/)).toBeInTheDocument()
    expect(within(section).getByText('-9%')).toBeInTheDocument()
    expect(within(section).getByText('2 dias')).toBeInTheDocument()
    expect(within(section).getByText('abaixo do esperado')).toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
    expect(screen.queryByText('Resumo operacional')).not.toBeInTheDocument()
  })

  it('primeiro ano (sem referência): um aviso único com a data; nada de "—"/"Baseline indisponível" nem blocos contra o esperado', async () => {
    vi.resetModules()
    const noBaselineAnomalies = {
      ...anomalyPayload,
      current_streak_days: 0,
      worst_level: null,
      expected_unavailable_reason: 'REFERENCE_YEAR_INCOMPLETE',
      daily: anomalyPayload.daily.map((day) => ({ ...day, expected_production_kwh: null, level: null, deviation_percent: null })),
    }
    installApiMock({
      fetchAnomalyHistory: vi.fn(async () => jsonResponse(noBaselineAnomalies)),
      fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(fallbackPhotovoltaicSummaryPayload)),
    })

    await renderProductionPage()

    const note = await screen.findByRole('note')
    expect(note).toHaveTextContent('Produção esperada disponível a partir de 14/03/2027')
    await screen.findByRole('heading', { level: 2, name: 'Leitura do período' })
    expect(screen.queryByRole('heading', { level: 2, name: 'Último dia contra o esperado' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Diagnóstico de produção do período' })).not.toBeInTheDocument()
    expect(screen.queryByText('Baseline indisponível')).not.toBeInTheDocument()
    expect(screen.queryByText('Desempenho médio')).not.toBeInTheDocument()
  })

  it('ordem: ciclos de fatura → histórico diário → leitura do período → último dia → diagnóstico', async () => {
    vi.resetModules()
    installApiMock()

    await renderProductionPage()

    const diagnosisSection = await screen.findByRole('region', { name: 'Diagnóstico de produção do período' })
    await waitFor(() => {
      expect(within(diagnosisSection).getByRole('heading', { level: 2, name: 'Diagnóstico: perda recorrente de produção' })).toBeInTheDocument()
    })
    const order = [
      screen.getByRole('heading', { level: 2, name: 'Placas × distribuidora, ciclo a ciclo' }),
      screen.getByRole('heading', { level: 2, name: 'Histórico de produção' }),
      screen.getByRole('heading', { level: 2, name: 'Leitura do período' }),
      screen.getByRole('heading', { level: 2, name: 'Último dia contra o esperado' }),
      diagnosisSection,
    ]
    for (let index = 1; index < order.length; index += 1) {
      expect(order[index - 1].compareDocumentPosition(order[index]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
  })
})

describe('ProductionPage — seção "Placas × distribuidora, ciclo a ciclo"', () => {
  it('renderiza as colunas do histórico de ciclos, não o banner de erro', async () => {
    vi.resetModules()
    installApiMock()

    await renderProductionPage()

    const sectionTitle = await screen.findByText('Placas × distribuidora, ciclo a ciclo')
    const section = sectionTitle.closest('section') as HTMLElement

    await waitFor(() => {
      expect(within(section).queryByRole('alert')).not.toBeInTheDocument()
    })

    // Os 3 ciclos de `monthlyHistoryPayload`, mais recente primeiro, com as
    // placas e o registro da Equatorial lado a lado (ADR-083, etapa 3).
    const latest = (await within(section).findByRole('heading', { level: 3, name: /mai\/26/ })).closest('li') as HTMLElement
    expect(within(latest).getByText('16/04 a 15/05')).toBeInTheDocument()
    expect(within(latest).getByText('500 kWh')).toBeInTheDocument()
    expect(within(latest).getByText('190 kWh')).toBeInTheDocument()
    expect(within(section).getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent?.slice(0, 6))).toEqual([
      'mai/26',
      'abr/26',
      'mar/26',
    ])
    // mai/26 tem missing_days: 3 no payload — único ciclo com o selo de lacuna.
    expect(within(section).getAllByText(/sem leitura do inversor/)).toHaveLength(1)
  })

  it('mostra o esqueleto de carregamento enquanto /reports/monthly/history está em voo, depois as colunas reais (sucesso)', async () => {
    vi.resetModules()
    let resolveFetch: (value: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve
    })
    installApiMock({ fetchMonthlyProductionHistory: vi.fn(async () => pending) })

    await renderProductionPage()

    const sectionTitle = await screen.findByText('Placas × distribuidora, ciclo a ciclo')
    const section = sectionTitle.closest('section') as HTMLElement
    expect(within(section).queryByRole('heading', { level: 3 })).not.toBeInTheDocument()

    resolveFetch(jsonResponse(monthlyHistoryPayload))

    expect(await within(section).findByRole('heading', { level: 3, name: /mar\/26/ })).toBeInTheDocument()
  })

  it('mostra RetryableError (não as colunas) quando fetchMonthlyProductionHistory falha, sem travar o resto do módulo, e refaz o fetch ao clicar em "Tentar novamente"', async () => {
    vi.resetModules()
    const fetchMonthlyProductionHistoryMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: 'boom' }, 500))
      .mockResolvedValueOnce(jsonResponse(monthlyHistoryPayload))
    installApiMock({ fetchMonthlyProductionHistory: fetchMonthlyProductionHistoryMock })

    await renderProductionPage()

    const sectionTitle = await screen.findByText('Placas × distribuidora, ciclo a ciclo')
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

    expect(await within(section).findByRole('heading', { level: 3, name: /mai\/26/ })).toBeInTheDocument()
    expect(fetchMonthlyProductionHistoryMock).toHaveBeenCalledTimes(2)
  })
})

describe('ProductionPage — "Histórico de produção" e a comparação do último dia', () => {
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

    // A comparação com o esperado só existe depois que o histórico responde
    // (é ele que diz se há referência) — nada de régua vazia enquanto carrega.
    expect(screen.queryByRole('heading', { level: 2, name: 'Último dia contra o esperado' })).not.toBeInTheDocument()

    resolveFetch(jsonResponse(anomalyPayload))
    const latestSection = (await screen.findByRole('heading', { level: 2, name: 'Último dia contra o esperado' })).closest('section') as HTMLElement

    // `anomalyPayload.daily` traz dois dias; o mais recente (2026-07-30) tem
    // actual_production_kwh=40 e expected_production_kwh=44 — mesma escala
    // diária.
    await waitFor(() => {
      expect(within(latestSection).getByText('Produção de 30/07/2026 vs. esperada')).toBeInTheDocument()
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

    // Sem histórico não há o que comparar: a comparação com o esperado não
    // aparece (nem duplica o erro), e volta quando o histórico responde.
    expect(screen.queryByRole('heading', { level: 2, name: 'Último dia contra o esperado' })).not.toBeInTheDocument()

    fireEvent.click(within(historySection).getByRole('button', { name: 'Tentar novamente' }))

    await waitFor(() => {
      expect(within(historySection).getByRole('slider')).toBeInTheDocument()
    })
    expect(await screen.findByRole('heading', { level: 2, name: 'Último dia contra o esperado' })).toBeInTheDocument()
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

  it('mostra o gráfico de histórico com produção real, sem linha de referência esperada e sem cair no fallback de dados insuficientes, quando a usina tem produção real mas não tem baseline sazonal', async () => {
    vi.resetModules()

    const noBaselineAnomalyPayload = {
      plant_id: 'plant-1',
      days_analyzed: 1,
      current_streak_days: 0,
      worst_level: null,
      expected_unavailable_reason: 'REFERENCE_YEAR_INCOMPLETE',
      period_yield_kwh_per_kwh_m2: null,
      yield_atypical_threshold_percent: '20',
      period_yield_sample_days: 0,
      daily: [
        {
          date: '2026-07-30',
          actual_production_kwh: 40,
          expected_production_kwh: null,
          level: null,
          deviation_percent: null,
          irradiation_kwh_m2: null,
          yield_kwh_per_kwh_m2: null,
          yield_deviation_from_median_percent: null,
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
    expect(within(section).queryByText('Média diária esperada (baseline sazonal)')).not.toBeInTheDocument()
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

    await screen.findByRole('heading', { level: 3, name: /mai\/26/ })
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

describe('ProductionPage — gráfico diário e leitura do período juntos', () => {
  it('o gráfico diário vem sozinho com o seletor, e a leitura do período logo abaixo', async () => {
    vi.resetModules()
    installApiMock()

    await renderProductionPage()

    const historico = (await screen.findByRole('heading', { level: 2, name: 'Histórico de produção' })).closest('section') as HTMLElement
    const leituraSection = (await screen.findByRole('heading', { level: 2, name: 'Leitura do período' })).closest('section') as HTMLElement

    // Ordem no DOM: gráfico diário e, logo depois, a leitura do mesmo recorte.
    expect(historico.nextElementSibling).toBe(leituraSection)
    await waitFor(() => {
      expect(within(historico).getByRole('slider')).toBeInTheDocument()
    })
    expect(within(historico).getByRole('group', { name: 'Filtrar histórico diário' })).toBeInTheDocument()
    // Só o gráfico: a leitura do período (média, tendência, gatilho) fica abaixo.
    expect(within(historico).queryByText('Tendência do recorte')).not.toBeInTheDocument()
    const leitura = screen.getByRole('heading', { level: 2, name: 'Leitura do período' }).closest('section') as HTMLElement
    expect(within(leitura).getByText('Tendência do recorte')).toBeInTheDocument()
    expect(within(leitura).queryByRole('slider')).not.toBeInTheDocument()
  })

  it('o seletor do gráfico muda também a leitura do período (um recorte só)', async () => {
    vi.resetModules()
    installApiMock()

    await renderProductionPage()

    const historico = (await screen.findByRole('heading', { level: 2, name: 'Histórico de produção' })).closest('section') as HTMLElement
    await waitFor(() => {
      expect(within(historico).getByRole('button', { name: '30 dias' })).toBeInTheDocument()
    })
    fireEvent.click(within(historico).getByRole('button', { name: '30 dias' }))

    expect(within(historico).getByRole('button', { name: '30 dias' })).toHaveAttribute('aria-pressed', 'true')
    const leitura = screen.getByRole('heading', { level: 2, name: 'Leitura do período' }).closest('section') as HTMLElement
    expect(within(leitura).getByText(/^Últimos \d+ dias em foco$/)).toBeInTheDocument()
    expect(within(leitura).getByText('Precisa de janela anterior de 30 dias para comparar tendência.')).toBeInTheDocument()
  })
})

describe('ProductionPage — leitura do período em orientação paisagem', () => {
  it('com rendimento disponível, "Produção diária" e o rendimento médio ficam lado a lado num grid de duas colunas', async () => {
    vi.resetModules()
    installApiMock({
      fetchAnomalyHistory: vi.fn(async () =>
        jsonResponse({ ...anomalyPayload, period_yield_kwh_per_kwh_m2: '4.1', period_yield_sample_days: 87 })
      ),
    })

    await renderProductionPage()

    const leitura = (await screen.findByRole('heading', { level: 2, name: 'Leitura do período' })).closest('section') as HTMLElement
    const diaria = within(leitura).getByText('Produção diária')
    const rendimento = within(leitura).getByText(/Rendimento médio da janela analisada \(87 dias\)/)
    const grid = diaria.closest('[class*="lg:grid-cols-[minmax"]') as HTMLElement
    expect(grid).not.toBeNull()
    expect(grid).toContainElement(rendimento)
    // Os dois cards são filhos diretos do mesmo grid (colunas irmãs).
    expect(grid.children).toHaveLength(2)
  })

  it('sem rendimento (sem irradiância), "Produção diária" ocupa a largura toda — sem coluna vazia', async () => {
    vi.resetModules()
    installApiMock()

    await renderProductionPage()

    const leitura = (await screen.findByRole('heading', { level: 2, name: 'Leitura do período' })).closest('section') as HTMLElement
    const diaria = within(leitura).getByText('Produção diária')
    expect(diaria.closest('[class*="lg:grid-cols-[minmax"]')).toBeNull()
    expect(within(leitura).queryByText(/Rendimento médio da janela analisada/)).not.toBeInTheDocument()
  })
})
