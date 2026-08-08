import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste (ver `LoginPage.test.tsx`).
vi.mock('../env', () => ({
  API_URL: 'https://api.example.test',
}))

// `PlantContext` busca `/plants` ao montar (ADR-069, Etapa C) — uma única
// usina, para preservar o comportamento anterior a esta etapa em todos os
// testes que não são especificamente sobre seleção de usina.
const singlePlant = {
  id: '00000000-0000-0000-0000-000000000000',
  name: 'Usina de teste',
  installedPowerKwp: null,
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const executivePayload = {
  plant_id: 'plant-1',
  status: 'ATTENTION',
  headline: 'Ciclo requer acompanhamento; índice de saúde 70/100.',
  priority_actions: ['Revisar consumo importado'],
  current_cycle: {
    reference_month: '2026-07',
    quality: { missing_days: 0, provisional_days: 0, incomplete_days: 0, unavailable_days: 0 },
    indicators: {
      cycle_production_kwh: 500,
      imported_kwh: 120,
      injected_kwh: 80,
      estimated_self_consumption_kwh: 420,
      estimated_total_consumption_kwh: 540,
      self_consumption_rate_percent: 84,
      self_sufficiency_rate_percent: 77.7,
      grid_dependency_rate_percent: 22.3,
      exported_generation_rate_percent: 16,
      credit_coverage_rate_percent: 100,
      // Consistente com a fórmula real do backend: bill_energy_component_brl
      // = total_amount_brl - public_lighting_brl (ver
      // intelligence/energy_engine.py::analyze_energy_cycle) — 420.71 - 30.21.
      bill_energy_component_brl: 390.5,
      health_score: 70,
      total_amount_brl: 420.71,
      public_lighting_brl: 30.21,
      tariff_with_taxes_brl_kwh: 0.85,
      tariff_without_taxes_brl_kwh: 0.6,
      credit_balance_kwh: 63.98,
      estimated_savings_brl: 120.4,
      savings_unavailable_reason: null,
    },
    diagnostics: [],
  },
  trend: null,
}

const photovoltaicSummaryPayload = {
  plant_id: 'plant-1',
  performance: {
    dc_capacity_kwp: '10.000',
    performance_ratio: '0.8200',
    temperature_corrected_performance_ratio: '0.8500',
    final_yield_kwh_per_kwp: '4.400',
    reporting_availability_ratio: '0.9800',
  },
  performance_unavailable_reason: null,
  baseline: {
    baseline_median_performance_ratio: '0.8000',
    clear_sky_poa_p90_kwh_m2: '5.500',
    degradation_percent: '-1.20',
    annualized_degradation_percent: '-0.60',
    degradation_status: 'STABLE',
  },
  baseline_unavailable_reason: null,
  reference_complete_on: null,
  losses: [
    { category: 'COMMUNICATION', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'UNAVAILABILITY', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'CLIPPING', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'SOILING', evidence_level: 'POSSIBLE', estimated_loss_percent: '1.50', evidence_codes: ['SOILING_TREND'], limitation: null },
    { category: 'SHADING', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
    { category: 'TEMPERATURE', evidence_level: 'LIKELY', estimated_loss_percent: '2.30', evidence_codes: ['HIGH_CELL_TEMP'], limitation: null },
    { category: 'DEGRADATION', evidence_level: 'NOT_ASSESSABLE', estimated_loss_percent: null, evidence_codes: [], limitation: 'Baseline insuficiente para isolar degradação.' },
    { category: 'UNEXPLAINED', evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00', evidence_codes: [], limitation: null },
  ],
  losses_unavailable_reason: null,
  // ADR-068, seção 3: produção esperada diária calculada e quantizada no
  // backend a partir dos mesmos registros de `performance`/`baseline` acima
  // (10 kWp × 5.5 kWh/m² × 0.80 = 44.000 kWh/dia).
  expected_daily_production_kwh: '44.000',
  expected_daily_production_model_version: 'MPLACAS_EXPECTED_DAILY_PRODUCTION_V1',
  expected_daily_production_nature: 'SEASONAL_CLEAR_SKY_P90_ENVELOPE',
  expected_daily_production_unavailable_reason: null,
}

// Usina nova (o caso real do bug corrigido nesta etapa): produção real já é
// coletada, mas o primeiro ano de referência ainda não fechou — sem baseline
// sazonal, `expectedProduction.available` é `false` em `/photovoltaic/summary`.
// Usado para provar que `fetchAnomalies` não fica preso esperando por este
// resultado (ver `DashboardPage — histórico de produção não depende mais do
// baseline sazonal` abaixo).
const fallbackPhotovoltaicSummaryPayload = {
  plant_id: 'plant-1',
  performance: null,
  performance_unavailable_reason: 'NO_PERFORMANCE_RESULTS',
  baseline: null,
  baseline_unavailable_reason: 'REFERENCE_YEAR_INCOMPLETE',
  reference_complete_on: '2027-03-14',
  losses: null,
  losses_unavailable_reason: 'NO_LOSS_ASSESSMENTS',
  expected_daily_production_kwh: null,
  expected_daily_production_model_version: null,
  expected_daily_production_nature: null,
  expected_daily_production_unavailable_reason: 'REFERENCE_YEAR_INCOMPLETE',
}

const anomalyPayload = {
  plant_id: 'plant-1',
  days_analyzed: 3,
  current_streak_days: 2,
  worst_level: 'ATTENTION',
  expected_unavailable_reason: null,
  daily: [
    {
      date: '2026-07-29',
      actual_production_kwh: 38,
      expected_production_kwh: 44,
      level: 'ATTENTION',
      deviation_percent: -13.6,
      irradiation_kwh_m2: null,
    },
    {
      date: '2026-07-30',
      actual_production_kwh: 40,
      expected_production_kwh: 44,
      level: 'NORMAL',
      deviation_percent: -9,
      irradiation_kwh_m2: null,
    },
  ],
}

// Retorno do investimento indisponível (CAPEX nunca registrado) — payload
// default de `fetchFinancialReturn` para todos os testes que não são
// especificamente sobre a seção de retorno do investimento (extraído de 4
// blocos de mock idênticos que existiam antes da Etapa 0, um por `vi.doMock`
// inline).
const financialReturnUnavailablePayload = {
  plant_id: 'plant-1',
  investment_amount_brl: null,
  investment_recorded_on: null,
  commissioned_on: null,
  accumulated_savings_brl: null,
  average_monthly_savings_brl: null,
  cycles_counted: null,
  cycles_expected: null,
  roi_percent: null,
  payback_projection_months: null,
  unavailable_reason: 'INVESTMENT_NOT_REGISTERED',
  payback_unavailable_reason: 'INVESTMENT_NOT_REGISTERED',
}

// Histórico de produção por ciclo de faturamento (`GET /reports/monthly/history`,
// ver `lib/dashboard/monthly-history-contracts.ts`) — payload default de
// `fetchMonthlyProductionHistory` (Etapa 0: nenhum dos 4 blocos de mock
// pré-existentes incluía esta função, então `MonthlyProductionSection`
// renderizava o banner de erro capturado pelo `catch` de
// `fetchMonthlyHistoryData` em todo teste da página, sem nenhuma asserção
// notando isso). 3 ciclos em ordem cronológica, o último com uma lacuna de
// telemetria (`missing_days: 3`) para exercitar o selo "dados parciais" no
// fluxo real da página.
const monthlyHistoryPayload = {
  plant_id: 'plant-1',
  limit: 12,
  cycles_returned: 3,
  cycles: [
    {
      reference_month: '2026-03',
      bill_id: '33333333-3333-3333-3333-333333333333',
      status: 'STABLE',
      production_kwh: '980.00',
      quality: { missing_days: 0, provisional_days: 0, incomplete_days: 0, unavailable_days: 0 },
    },
    {
      reference_month: '2026-04',
      bill_id: '44444444-4444-4444-4444-444444444444',
      status: 'STABLE',
      production_kwh: '1050.00',
      quality: { missing_days: 0, provisional_days: 1, incomplete_days: 0, unavailable_days: 0 },
    },
    {
      reference_month: '2026-05',
      bill_id: '55555555-5555-5555-5555-555555555555',
      status: 'STABLE',
      production_kwh: '500.00',
      quality: { missing_days: 3, provisional_days: 0, incomplete_days: 0, unavailable_days: 0 },
    },
  ],
}

// Helper único de mock de `../lib/api` (Etapa 0: antes existiam 4 blocos
// `vi.doMock('../lib/api', ...)` divergentes — este `installApiMock` mais o
// `renderDashboard` abaixo, mais 3 blocos inline em testes específicos — cada
// um redefinindo os 6 exports do módulo do zero, sem nenhum incluir
// `fetchMonthlyProductionHistory`). Todos os pontos de mock da suíte passam a
// chamar esta função: os testes felizes usam só o default de cada export: os
// poucos testes que precisam de um comportamento diferente (contagem de
// chamadas, path/plant_id capturado, payload alternativo) sobrescrevem
// exatamente o export que importa via `overrides`, sem duplicar os outros 5.
interface ApiMockOverrides {
  // Atalho para o caso mais comum (só o corpo de `/energy/executive/latest`
  // muda) — equivalente ao antigo parâmetro posicional de `installApiMock`/
  // `renderDashboard`. Ignorado se `fetchExecutiveDashboard` também for
  // informado.
  executivePayload?: unknown
  fetchExecutiveDashboard?: (plantId: string) => Promise<Response>
  fetchAnomalyHistory?: (plantId: string, days?: number) => Promise<Response>
  fetchPhotovoltaicSummary?: (plantId: string) => Promise<Response>
  fetchFinancialReturn?: (plantId: string) => Promise<Response>
  fetchMonthlyProductionHistory?: (plantId: string, limit?: number) => Promise<Response>
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
    fetchPhotovoltaicSummary:
      overrides.fetchPhotovoltaicSummary ?? vi.fn(async () => jsonResponse(photovoltaicSummaryPayload)),
    fetchFinancialReturn:
      overrides.fetchFinancialReturn ?? vi.fn(async () => jsonResponse(financialReturnUnavailablePayload)),
    fetchMonthlyProductionHistory:
      overrides.fetchMonthlyProductionHistory ?? vi.fn(async () => jsonResponse(monthlyHistoryPayload)),
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
  it('compara a produção real do último dia vs. a esperada do mesmo dia em um único bullet chart', async () => {
    vi.resetModules()
    await renderDashboard()

    // `anomalyPayload.daily` traz dois dias; o mais recente (2026-07-30) tem
    // actual_production_kwh=40 e expected_production_kwh=44 — mesma escala
    // diária, não mais o total do ciclo (500 kWh) comparado com uma média.
    const sectionTitle = await screen.findByText('Produção do último dia vs. esperada')
    const section = sectionTitle.closest('section') as HTMLElement

    expect(within(section).getByText('40 kWh')).toBeInTheDocument()
    expect(within(section).getByText(/esperado 44 kWh/)).toBeInTheDocument()
    // (40 - 44) / 44 * 100 ≈ -9,1%
    expect(within(section).getByText(/-9,1%/)).toBeInTheDocument()

    // A produção total do ciclo (500 kWh) não desapareceu — continua visível
    // no nó "Produção" do diagrama de fluxo de energia.
    expect(screen.queryByText('Produção no ciclo')).not.toBeInTheDocument()
  })

  it('autoconsumo/injetada/importada aparecem em um único componente de visualização (EnergyFlowDiagram)', async () => {
    vi.resetModules()
    await renderDashboard()

    await screen.findByText('Produção do último dia vs. esperada')

    // O diagrama de fluxo é o único visual mantido — os outros dois visuais
    // redundantes (composição em barra e donut de origem do consumo) não
    // devem aparecer na página.
    expect(await screen.findByText('Fluxo de energia no ciclo')).toBeInTheDocument()
    expect(screen.queryByText('Composição da produção')).not.toBeInTheDocument()
    expect(screen.queryByText('Origem do consumo')).not.toBeInTheDocument()
  })

  // Etapa 7: o conteúdo detalhado do bloco financeiro (decomposição da
  // fatura, três subgrupos "Custo do ciclo"/"Tarifas"/"Créditos de energia",
  // regra de nunca mostrar R$ 0,00 de economia sem tarifa registrada, estado
  // de erro do retorno do investimento) foi extraído para `FinancialSection`
  // e a cobertura exaustiva foi junto — ver `FinancialSection.test.tsx`. O
  // teste abaixo é o mínimo de integração que continua fazendo sentido aqui:
  // prova que `DashboardPage` passa os dados certos (`indicators` do ciclo
  // corrente, o recurso `financialReturn`) para a seção extraída, e que ela
  // aparece no lugar certo da página (duas seções irmãs, "Financeiro" e
  // "Retorno do investimento").
  it('passa os dados do ciclo e do retorno do investimento para a FinancialSection extraída (Etapa 7)', async () => {
    vi.resetModules()
    await renderDashboard()

    const financeiroTitle = await screen.findByText('Financeiro')
    const section = financeiroTitle.parentElement as HTMLElement

    expect(within(section).getByText('Custo do ciclo')).toBeInTheDocument()
    expect(within(section).getByText('Tarifas')).toBeInTheDocument()
    expect(within(section).getByText('Créditos de energia')).toBeInTheDocument()

    // Um valor de cada subgrupo, prova de que `indicators` chega intacto à
    // seção extraída.
    expect(within(section).getByText(/R\$\s*420,71/)).toBeInTheDocument()
    expect(within(section).getByText(/0,85/)).toBeInTheDocument()
    expect(within(section).getByText(/63,98/)).toBeInTheDocument()

    // "Retorno do investimento" é uma seção irmã de "Financeiro", dentro do
    // mesmo componente (`FinancialSection`) — continua aparecendo na página
    // (o texto se repete no `<h2>` da seção e no rótulo interno do card de
    // `FinancialReturnSection`; a busca é restrita ao heading).
    expect(
      await screen.findByRole('heading', { level: 2, name: 'Retorno do investimento' })
    ).toBeInTheDocument()
  })

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

  it('mostra o status de anomalia (streak) dentro do histórico de produção, não mais duplicado ao lado (Etapa 1.4)', async () => {
    vi.resetModules()
    await renderDashboard()

    const sectionTitle = await screen.findByText('Histórico de produção')
    const section = sectionTitle.parentElement as HTMLElement

    await waitFor(() => {
      expect(within(section).getByText(/dias seguidos com produção abaixo do esperado/)).toBeInTheDocument()
    })
  })
})

describe('DashboardPage — desredundância (Etapa 1.4)', () => {
  it('a frase de streak de anomalia aparece exatamente uma vez na página', async () => {
    vi.resetModules()
    await renderDashboard()

    await screen.findByText('Financeiro')

    await waitFor(() => {
      expect(screen.getAllByText(/dias seguidos com produção abaixo do esperado/)).toHaveLength(1)
    })
  })

  it('não renderiza mais a seção "Energia e produção" (redundante com o diagrama de fluxo)', async () => {
    vi.resetModules()
    await renderDashboard()

    await screen.findByText('Financeiro')

    expect(screen.queryByText('Energia e produção')).not.toBeInTheDocument()
    // Os mesmos fatos continuam visíveis, só que uma única vez, no diagrama de fluxo.
    expect(screen.getByText('Fluxo de energia no ciclo')).toBeInTheDocument()
  })

  it('importada, injetada, autoconsumo e consumo aparecem em uma única visualização — nenhum card avulso duplica os rótulos de "Energia e produção" removidos (Etapa 3.3)', async () => {
    vi.resetModules()
    await renderDashboard()

    await screen.findByText('Financeiro')

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

    await findByText('Financeiro')
    expect(executiveCalls).toBe(2)
  })

  // Etapa 6: antes, o retry do erro global refazia só o fetch executivo
  // (`executive.refetch`) — os outros 4 recursos ficavam presos no estado
  // antigo mesmo depois do usuário pedir para tentar de novo. Prova que os 5
  // recursos (`executive`, `anomalies`, `pvSummaryResource`, `financialReturn`,
  // `monthlyHistory`) são refeitos juntos (`refreshAll`), não só o que errou.
  it('refaz os 5 fetches (não só o executivo) ao clicar em "Tentar novamente" no erro global', async () => {
    vi.resetModules()
    let executiveCalls = 0
    const fetchAnomalyHistoryMock = vi.fn(async () => jsonResponse(anomalyPayload))
    const fetchPhotovoltaicSummaryMock = vi.fn(async () => jsonResponse(photovoltaicSummaryPayload))
    const fetchFinancialReturnMock = vi.fn(async () => jsonResponse(financialReturnUnavailablePayload))
    const fetchMonthlyProductionHistoryMock = vi.fn(async () => jsonResponse(monthlyHistoryPayload))
    installApiMock({
      fetchExecutiveDashboard: vi.fn(async () => {
        executiveCalls += 1
        if (executiveCalls === 1) return jsonResponse({ error: 'boom' }, 500)
        return jsonResponse(executivePayload)
      }),
      fetchAnomalyHistory: fetchAnomalyHistoryMock,
      fetchPhotovoltaicSummary: fetchPhotovoltaicSummaryMock,
      fetchFinancialReturn: fetchFinancialReturnMock,
      fetchMonthlyProductionHistory: fetchMonthlyProductionHistoryMock,
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
      expect(fetchPhotovoltaicSummaryMock).toHaveBeenCalledTimes(1)
      expect(fetchFinancialReturnMock).toHaveBeenCalledTimes(1)
      expect(fetchMonthlyProductionHistoryMock).toHaveBeenCalledTimes(1)
    })

    const retryButton = getByRole('button', { name: 'Tentar novamente' })
    retryButton.click()

    await findByText('Financeiro')
    expect(executiveCalls).toBe(2)
    await waitFor(() => {
      expect(fetchAnomalyHistoryMock).toHaveBeenCalledTimes(2)
      expect(fetchPhotovoltaicSummaryMock).toHaveBeenCalledTimes(2)
      expect(fetchFinancialReturnMock).toHaveBeenCalledTimes(2)
      expect(fetchMonthlyProductionHistoryMock).toHaveBeenCalledTimes(2)
    })
  })
})

describe('DashboardPage — grid real no breakpoint md (Etapa 1.2)', () => {
  it('pelo menos duas seções distintas declaram md:col-span diferente de 6 (grid de 6 colunas)', async () => {
    vi.resetModules()
    const { container } = await renderDashboard()

    await screen.findByText('Financeiro')

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

describe('DashboardPage — re-busca dados quando a usina ativa muda (ADR-069, Etapa C)', () => {
  it('refaz as chamadas de dados com o novo plant_id quando o PlantContext resolve outra usina', async () => {
    vi.resetModules()

    const secondPlant = {
      id: '00000000-0000-0000-0000-000000000002',
      name: 'Segunda usina',
      installedPowerKwp: null,
    }
    const executiveCallsPlantIds: string[] = []

    installApiMock({
      fetchExecutiveDashboard: vi.fn(async (plantId: string) => {
        executiveCallsPlantIds.push(plantId)
        return jsonResponse(executivePayload)
      }),
      fetchPlants: vi.fn(async () => [singlePlant, secondPlant]),
    })

    const { DashboardPage } = await import('./DashboardPage')
    const { AuthProvider } = await import('../contexts/AuthContext')
    const { PlantProvider, usePlant } = await import('../contexts/PlantContext')

    function PlantSwitcher() {
      const { selectPlant } = usePlant()
      return (
        <button onClick={() => selectPlant(secondPlant.id)}>trocar-usina</button>
      )
    }

    render(
      <MemoryRouter>
        <AuthProvider>
          <PlantProvider>
            <PlantSwitcher />
            <main>
              <DashboardPage />
            </main>
          </PlantProvider>
        </AuthProvider>
      </MemoryRouter>
    )

    await screen.findByText('Financeiro')
    expect(executiveCallsPlantIds).toEqual([singlePlant.id])

    screen.getByRole('button', { name: 'trocar-usina' }).click()

    await waitFor(() => {
      expect(executiveCallsPlantIds).toEqual([singlePlant.id, secondPlant.id])
    })
  })
})

describe('DashboardPage — histórico de produção não depende mais do baseline sazonal (contrato 200 sempre)', () => {
  it('busca /energy/anomalies/latest assim que há plantId, sem esperar expectedProduction.available e sem parâmetros extras (ex.: o antigo expected_daily_production_kwh)', async () => {
    vi.resetModules()
    const fetchAnomalyHistoryMock = vi.fn(async () => jsonResponse(anomalyPayload))

    installApiMock({
      fetchAnomalyHistory: fetchAnomalyHistoryMock,
      // `/photovoltaic/summary` responde SEM baseline (usina nova) — a busca
      // de anomalias não pode esperar por esse resultado.
      fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(fallbackPhotovoltaicSummaryPayload)),
    })

    const { DashboardPage } = await import('./DashboardPage')
    const { AuthProvider } = await import('../contexts/AuthContext')
    const { PlantProvider } = await import('../contexts/PlantContext')

    render(
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

    await waitFor(() => {
      expect(fetchAnomalyHistoryMock).toHaveBeenCalled()
    })
    // A página chama só com `plantId` — nenhum segundo argumento (como o
    // antigo `expected_daily_production_kwh`) é passado; `days` fica a
    // cargo do default de `fetchAnomalyHistory` em `lib/api.ts`.
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

    const { DashboardPage } = await import('./DashboardPage')
    const { AuthProvider } = await import('../contexts/AuthContext')
    const { PlantProvider } = await import('../contexts/PlantContext')

    render(
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

    const sectionTitle = await screen.findByText('Histórico de produção')
    const section = sectionTitle.parentElement as HTMLElement

    await waitFor(() => {
      expect(within(section).getByRole('slider')).toBeInTheDocument()
    })
    expect(within(section).getByText('40 kWh')).toBeInTheDocument()
    expect(within(section).queryByText('Esperado')).not.toBeInTheDocument()
    expect(within(section).queryByText(/histórico de desempenho insuficiente/)).not.toBeInTheDocument()
    expect(within(section).queryByText(/primeiro ano de referência/)).not.toBeInTheDocument()
  })
})

describe('DashboardPage — seção "Produção por ciclo de faturamento" (Etapa 0)', () => {
  it('renderiza as barras do histórico de ciclos, não o banner de erro (nenhum mock de ../lib/api anterior incluía fetchMonthlyProductionHistory)', async () => {
    vi.resetModules()
    await renderDashboard()

    const sectionTitle = await screen.findByText('Produção por ciclo de faturamento')
    const section = sectionTitle.closest('section') as HTMLElement

    // Antes da Etapa 0, `fetchMonthlyProductionHistory` não existia em
    // nenhum mock de `../lib/api` — chamá-la lançava um `TypeError`
    // capturado por `fetchMonthlyHistoryData`, que fazia esta seção
    // renderizar `RetryableError` (`role="alert"`) em vez do `BarList` real.
    await waitFor(() => {
      expect(within(section).queryByRole('alert')).not.toBeInTheDocument()
    })

    // Os 3 ciclos de `monthlyHistoryPayload` (default de `installApiMock`)
    // aparecem como barras reais, em ordem cronológica, com o valor formatado.
    expect(within(section).getAllByRole('progressbar')).toHaveLength(3)
    expect(within(section).getByText('mar/26')).toBeInTheDocument()
    expect(within(section).getByText('abr/26')).toBeInTheDocument()
    expect(within(section).getByText('mai/26')).toBeInTheDocument()
    expect(within(section).getByText('980 kWh')).toBeInTheDocument()
    expect(within(section).getByText('1.050 kWh')).toBeInTheDocument()
    expect(within(section).getByText('500 kWh')).toBeInTheDocument()

    // mai/26 tem missing_days: 3 no payload — único ciclo com o selo de
    // dados parciais.
    expect(within(section).getAllByText('dados parciais')).toHaveLength(1)
  })

  it('mostra RetryableError (não as barras) quando fetchMonthlyProductionHistory falha, sem travar o resto do dashboard', async () => {
    vi.resetModules()
    installApiMock({
      fetchMonthlyProductionHistory: vi.fn(async () => jsonResponse({ error: 'boom' }, 500)),
    })

    const { DashboardPage } = await import('./DashboardPage')
    const { AuthProvider } = await import('../contexts/AuthContext')
    const { PlantProvider } = await import('../contexts/PlantContext')

    render(
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

    const sectionTitle = await screen.findByText('Produção por ciclo de faturamento')
    const section = sectionTitle.closest('section') as HTMLElement

    await waitFor(() => {
      expect(within(section).getByRole('alert')).toBeInTheDocument()
    })
    // Mensagem fixa vinda de `usePlantResource` (Etapa 3) — sem sufixo de status
    // HTTP: o detalhe técnico vai para o console, nunca para a tela (mesma
    // política de `ErrorBoundary.tsx`).
    expect(within(section).getByRole('alert')).toHaveTextContent(
      'Erro ao buscar histórico de produção.'
    )

    // O erro isolado desta seção não trava o restante da página.
    expect(await screen.findByText('Financeiro')).toBeInTheDocument()
  })
})
