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

// Variante do payload executivo sem tarifa registrada na fatura do ciclo —
// usada para garantir que a economia estimada nunca aparece como "R$ 0,00"
// (ver EstimatedSavingsCard e intelligence/energy_engine.py).
const executivePayloadWithoutTariff = {
  ...executivePayload,
  current_cycle: {
    ...executivePayload.current_cycle,
    indicators: {
      ...executivePayload.current_cycle.indicators,
      tariff_with_taxes_brl_kwh: null,
      tariff_without_taxes_brl_kwh: null,
      estimated_savings_brl: null,
      savings_unavailable_reason: 'TARIFF_NOT_AVAILABLE',
    },
  },
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

function installApiMock(executiveOverride: unknown = executivePayload) {
  vi.doMock('../lib/api', () => ({
    apiFetch: vi.fn(async (path: string) => {
      if (path.startsWith('/energy/executive/latest')) return jsonResponse(executiveOverride)
      if (path.startsWith('/energy/anomalies/latest')) return jsonResponse(anomalyPayload)
      throw new Error(`unexpected apiFetch path in test: ${path}`)
    }),
    fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(photovoltaicSummaryPayload)),
    fetchFinancialReturn: vi.fn(async () =>
      jsonResponse({
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
      })
    ),
    fetchPlants: vi.fn(async () => [singlePlant]),
    configureApi: vi.fn(),
  }))
}

async function renderDashboard(executiveOverride: unknown = executivePayload) {
  installApiMock(executiveOverride)
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

  it('a seção Financeiro agrupa seus cards em três subgrupos rotulados, sem perder nenhum card (Frente H)', async () => {
    vi.resetModules()
    await renderDashboard()

    const financeiroTitle = await screen.findByText('Financeiro')
    const section = financeiroTitle.parentElement
    expect(section).not.toBeNull()

    // A grade achatada de 8 cards virou três subgrupos rotulados — "Custo do
    // ciclo" (decomposição da fatura em `StackedBar` + economia estimada),
    // "Tarifas" (2 cards) e "Créditos de energia" (2 cards) — todos os 8
    // valores financeiros originais continuam presentes e visíveis dentro da
    // seção, só que os três primeiros (total, energia, iluminação) agora
    // compõem uma única barra em vez de três cards soltos (ver Etapa 5).
    const custoGrid = within(section as HTMLElement)
      .getByText('Valor total da fatura')
      .closest('.grid')
    expect(custoGrid).not.toBeNull()
    expect(custoGrid!.children).toHaveLength(2)

    const tarifasGrid = within(section as HTMLElement).getByText('Tarifa com impostos').closest('.grid')
    expect(tarifasGrid).not.toBeNull()
    expect(tarifasGrid!.children).toHaveLength(2)

    const creditosGrid = within(section as HTMLElement).getByText('Saldo de créditos').closest('.grid')
    expect(creditosGrid).not.toBeNull()
    expect(creditosGrid!.children).toHaveLength(2)

    expect(within(section as HTMLElement).getByText('Custo do ciclo')).toBeInTheDocument()
    expect(within(section as HTMLElement).getByText('Tarifas')).toBeInTheDocument()
    expect(within(section as HTMLElement).getByText('Créditos de energia')).toBeInTheDocument()
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

  it('renderiza todos os valores financeiros novos com a unidade correta quando a fatura tem tarifa registrada', async () => {
    vi.resetModules()
    await renderDashboard()

    await screen.findByText('Financeiro')

    expect(screen.getByText('Valor total da fatura')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*420,71/)).toBeInTheDocument()

    expect(screen.getByText('Iluminação pública')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*30,21/)).toBeInTheDocument()

    // Decomposição da fatura: `StackedBar` com energia + iluminação pública,
    // sem um terceiro segmento "Outros encargos" porque, no mock,
    // energia + iluminação já reconstrói o total exatamente (mesma garantia
    // do backend real — ver `intelligence/energy_engine.py`).
    expect(screen.getByText('Componente energia')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*390,50/)).toBeInTheDocument()
    expect(screen.queryByText('Outros encargos')).not.toBeInTheDocument()

    const billBar = screen.getByRole('img', { name: /Total R\$\s*420,71/ })
    expect(billBar).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Componente energia R$ 390,50'),
    )
    expect(billBar).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Iluminação pública R$ 30,21'),
    )

    const tariffWithTaxesLabel = screen.getByText('Tarifa com impostos')
    const tariffWithTaxesCard = tariffWithTaxesLabel.closest('div') as HTMLElement
    expect(within(tariffWithTaxesCard).getByText(/0,85/)).toBeInTheDocument()
    expect(within(tariffWithTaxesCard).getByText('R$/kWh')).toBeInTheDocument()

    const tariffWithoutTaxesLabel = screen.getByText('Tarifa sem impostos')
    const tariffWithoutTaxesCard = tariffWithoutTaxesLabel.closest('div') as HTMLElement
    expect(within(tariffWithoutTaxesCard).getByText(/^0,6$/)).toBeInTheDocument()
    expect(within(tariffWithoutTaxesCard).getByText('R$/kWh')).toBeInTheDocument()

    expect(screen.getByText('Saldo de créditos')).toBeInTheDocument()
    expect(screen.getByText(/63,98/)).toBeInTheDocument()

    expect(screen.getByText('Cobertura de créditos')).toBeInTheDocument()

    expect(screen.getByText('Economia estimada')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*120,40/)).toBeInTheDocument()
  })

  it('nunca mostra R$ 0,00 de economia quando a fatura não tem tarifa registrada — mostra mensagem explícita', async () => {
    vi.resetModules()
    await renderDashboard(executivePayloadWithoutTariff)

    await screen.findByText('Financeiro')
    const savingsLabel = await screen.findByText('Economia estimada')
    const savingsCard = savingsLabel.closest('div') as HTMLElement

    expect(within(savingsCard).queryByText(/R\$\s*0,00/)).not.toBeInTheDocument()
    expect(
      within(savingsCard).getByText(/fatura deste ciclo não tem a tarifa com impostos registrada/)
    ).toBeInTheDocument()
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
    vi.doMock('../lib/api', () => ({
      apiFetch: vi.fn(async (path: string) => {
        if (path.startsWith('/energy/executive/latest')) {
          executiveCalls += 1
          if (executiveCalls === 1) return jsonResponse({ error: 'boom' }, 500)
          return jsonResponse(executivePayload)
        }
        if (path.startsWith('/energy/anomalies/latest')) return jsonResponse(anomalyPayload)
        throw new Error(`unexpected apiFetch path in test: ${path}`)
      }),
      fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(photovoltaicSummaryPayload)),
      fetchFinancialReturn: vi.fn(async () =>
        jsonResponse({
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
        })
      ),
      fetchPlants: vi.fn(async () => [singlePlant]),
      configureApi: vi.fn(),
    }))

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

    vi.doMock('../lib/api', () => ({
      apiFetch: vi.fn(async (path: string) => {
        if (path.startsWith('/energy/executive/latest')) {
          const url = new URL(path, 'https://example.test')
          executiveCallsPlantIds.push(url.searchParams.get('plant_id') ?? '')
          return jsonResponse(executivePayload)
        }
        if (path.startsWith('/energy/anomalies/latest')) return jsonResponse(anomalyPayload)
        throw new Error(`unexpected apiFetch path in test: ${path}`)
      }),
      fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(photovoltaicSummaryPayload)),
      fetchFinancialReturn: vi.fn(async () =>
        jsonResponse({
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
        })
      ),
      fetchPlants: vi.fn(async () => [singlePlant, secondPlant]),
      configureApi: vi.fn(),
    }))

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
  it('busca /energy/anomalies/latest assim que há plantId, sem esperar expectedProduction.available e sem o parâmetro deprecated na query', async () => {
    vi.resetModules()
    const anomalyCallPaths: string[] = []

    vi.doMock('../lib/api', () => ({
      apiFetch: vi.fn(async (path: string) => {
        if (path.startsWith('/energy/executive/latest')) return jsonResponse(executivePayload)
        if (path.startsWith('/energy/anomalies/latest')) {
          anomalyCallPaths.push(path)
          return jsonResponse(anomalyPayload)
        }
        throw new Error(`unexpected apiFetch path in test: ${path}`)
      }),
      // `/photovoltaic/summary` responde SEM baseline (usina nova) — a busca
      // de anomalias não pode esperar por esse resultado.
      fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(fallbackPhotovoltaicSummaryPayload)),
      fetchFinancialReturn: vi.fn(async () =>
        jsonResponse({
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
        })
      ),
      fetchPlants: vi.fn(async () => [singlePlant]),
      configureApi: vi.fn(),
    }))

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
      expect(anomalyCallPaths.length).toBeGreaterThan(0)
    })
    expect(anomalyCallPaths[0]).not.toContain('expected_daily_production_kwh')
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

    vi.doMock('../lib/api', () => ({
      apiFetch: vi.fn(async (path: string) => {
        if (path.startsWith('/energy/executive/latest')) return jsonResponse(executivePayload)
        if (path.startsWith('/energy/anomalies/latest')) return jsonResponse(noBaselineAnomalyPayload)
        throw new Error(`unexpected apiFetch path in test: ${path}`)
      }),
      fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(fallbackPhotovoltaicSummaryPayload)),
      fetchFinancialReturn: vi.fn(async () =>
        jsonResponse({
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
        })
      ),
      fetchPlants: vi.fn(async () => [singlePlant]),
      configureApi: vi.fn(),
    }))

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
