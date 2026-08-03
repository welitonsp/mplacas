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

function installApiMock() {
  vi.doMock('../lib/api', () => ({
    apiFetch: vi.fn(async (path: string) => {
      if (path.startsWith('/energy/executive/latest')) return jsonResponse(executivePayload)
      if (path.startsWith('/energy/anomalies/latest')) return jsonResponse(anomalyPayload)
      throw new Error(`unexpected apiFetch path in test: ${path}`)
    }),
    fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse(photovoltaicSummaryPayload)),
    configureApi: vi.fn(),
  }))
}

async function renderDashboard() {
  installApiMock()
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

  it('nenhum grid tem mais colunas declaradas do que filhos renderizados (seção Financeiro)', async () => {
    vi.resetModules()
    await renderDashboard()

    const financeiroTitle = await screen.findByText('Financeiro')
    const section = financeiroTitle.parentElement
    expect(section).not.toBeNull()
    const grid = within(section as HTMLElement).getByText('Componente energia da fatura').closest('.grid')
    expect(grid).not.toBeNull()

    // Grid de 1 coluna, sem breakpoints declarando mais colunas do que o único
    // card financeiro renderizado hoje.
    expect(grid!.className).toMatch(/grid-cols-1/)
    expect(grid!.className).not.toMatch(/sm:grid-cols-2|lg:grid-cols-3/)
    expect(grid!.children).toHaveLength(1)
  })

  it('mostra o status de anomalia (streak) dentro do bloco "Está indo bem?"', async () => {
    vi.resetModules()
    await renderDashboard()

    const sectionTitle = await screen.findByText('Produção real vs. esperada')
    const section = sectionTitle.parentElement as HTMLElement

    await waitFor(() => {
      expect(within(section).getByText(/dias seguidos com produção abaixo do esperado/)).toBeInTheDocument()
    })
  })
})
