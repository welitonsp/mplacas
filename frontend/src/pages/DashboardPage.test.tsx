import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL`/`VITE_PLANT_ID` no
// carregamento do módulo — não há `.env.local` no ambiente de teste (ver
// `LoginPage.test.tsx`).
vi.mock('../env', () => ({
  API_URL: 'https://api.example.test',
  PLANT_ID: '00000000-0000-0000-0000-000000000000',
}))

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
      bill_energy_component_brl: 350.5,
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
}

const anomalyPayload = {
  plant_id: 'plant-1',
  days_analyzed: 3,
  current_streak_days: 2,
  worst_level: 'ATTENTION',
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
    configureApi: vi.fn(),
  }))
}

async function renderDashboard(executiveOverride: unknown = executivePayload) {
  installApiMock(executiveOverride)
  const { DashboardPage } = await import('./DashboardPage')
  const { AuthProvider } = await import('../contexts/AuthContext')

  return render(
    <MemoryRouter>
      <AuthProvider>
        <DashboardPage />
      </AuthProvider>
    </MemoryRouter>
  )
}

describe('DashboardPage — reorganização em três blocos (Etapa 5)', () => {
  it('produção real ("Produção no ciclo") e produção esperada aparecem no mesmo container imediato', async () => {
    vi.resetModules()
    await renderDashboard()

    const realLabel = await screen.findByText('Produção no ciclo')
    const expectedLabel = await screen.findByText('Produção esperada (média diária)')

    const realCard = realLabel.closest('div')
    const expectedCard = expectedLabel.closest('div')
    expect(realCard).not.toBeNull()
    expect(expectedCard).not.toBeNull()

    // Ambos os cards precisam compartilhar o mesmo pai imediato (o grid que os
    // agrupa) — não é permitido que fiquem em seções separadas da página.
    expect(realCard!.parentElement).toBe(expectedCard!.parentElement)
  })

  it('autoconsumo/injetada/importada aparecem em um único componente de visualização (EnergyFlowDiagram)', async () => {
    vi.resetModules()
    await renderDashboard()

    await screen.findByText('Produção no ciclo')

    // O diagrama de fluxo é o único visual mantido — os outros dois visuais
    // redundantes (composição em barra e donut de origem do consumo) não
    // devem aparecer na página.
    expect(await screen.findByText('Fluxo de energia no ciclo')).toBeInTheDocument()
    expect(screen.queryByText('Composição da produção')).not.toBeInTheDocument()
    expect(screen.queryByText('Origem do consumo')).not.toBeInTheDocument()
  })

  it('a seção Financeiro tem exatamente um card por filho declarado no grid (Etapa 7)', async () => {
    vi.resetModules()
    await renderDashboard()

    const financeiroTitle = await screen.findByText('Financeiro')
    const section = financeiroTitle.parentElement
    expect(section).not.toBeNull()
    const grid = within(section as HTMLElement).getByText('Componente energia da fatura').closest('.grid')
    expect(grid).not.toBeNull()

    // Etapa 7 expandiu a seção — agora com múltiplas colunas em telas maiores,
    // mas o número de filhos do grid ainda precisa bater com os cards
    // efetivamente renderizados abaixo.
    expect(grid!.children).toHaveLength(8)
  })

  it('renderiza todos os valores financeiros novos com a unidade correta quando a fatura tem tarifa registrada', async () => {
    vi.resetModules()
    await renderDashboard()

    await screen.findByText('Financeiro')

    expect(screen.getByText('Valor total da fatura')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*420,71/)).toBeInTheDocument()

    expect(screen.getByText('Iluminação pública')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*30,21/)).toBeInTheDocument()

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
      configureApi: vi.fn(),
    }))

    const { DashboardPage } = await import('./DashboardPage')
    const { AuthProvider } = await import('../contexts/AuthContext')
    const { getByRole, findByRole, findByText } = render(
      <MemoryRouter>
        <AuthProvider>
          <DashboardPage />
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
