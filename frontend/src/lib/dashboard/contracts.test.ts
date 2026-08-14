import { describe, expect, it } from 'vitest'
import {
  classifyAnomalyErrorStatus,
  combineDiagnostics,
  latestNonNullProductionDate,
  parseAnomalyDaily,
  parseAnomalyDashboard,
  parseExecutiveDashboard,
  type AnomalyDailyPoint,
  type ExecutiveDashboardResponse,
} from './contracts'

function buildDaily(overrides: Partial<AnomalyDailyPoint> = {}): AnomalyDailyPoint {
  return {
    date: '2026-08-01',
    actual_production_kwh: 40,
    expected_production_kwh: 44,
    level: 'NORMAL',
    deviation_percent: -9,
    irradiation_kwh_m2: null,
    yield_kwh_per_kwh_m2: null,
    yield_deviation_from_median_percent: null,
    temperature_mean_c: null,
    diagnostics: [],
    ...overrides,
  }
}

describe('classifyAnomalyErrorStatus', () => {
  it('classifica 404 como ausência de dado coletado, não como falha do sistema', () => {
    expect(classifyAnomalyErrorStatus(404)).toBe('NOT_FOUND')
  })

  it('classifica 500 como falha do sistema', () => {
    expect(classifyAnomalyErrorStatus(500)).toBe('SERVER_ERROR')
  })

  it('classifica 401 como null (sessão expirada, tratada à parte)', () => {
    expect(classifyAnomalyErrorStatus(401)).toBeNull()
  })
})

describe('latestNonNullProductionDate', () => {
  it('retorna a data do último dia com produção não nula', () => {
    const daily = [
      buildDaily({ date: '2026-07-30', actual_production_kwh: 38 }),
      buildDaily({ date: '2026-07-31', actual_production_kwh: 41 }),
      buildDaily({ date: '2026-08-01', actual_production_kwh: null }),
    ]

    expect(latestNonNullProductionDate(daily)).toBe('2026-07-31')
  })

  it('retorna null quando nenhum dia tem produção coletada', () => {
    const daily = [buildDaily({ actual_production_kwh: null })]

    expect(latestNonNullProductionDate(daily)).toBeNull()
  })

  it('retorna null para lista vazia', () => {
    expect(latestNonNullProductionDate([])).toBeNull()
  })
})

function buildExecutivePayload(overrides: {
  currentCycleDiagnostics?: unknown[]
  trend?: unknown
} = {}): unknown {
  return {
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
        total_amount_brl: 400.5,
        public_lighting_brl: 50,
        tariff_with_taxes_brl_kwh: 0.85,
        tariff_without_taxes_brl_kwh: 0.6,
        credit_balance_kwh: 30,
        estimated_savings_brl: 120.4,
        savings_unavailable_reason: null,
      },
      diagnostics: overrides.currentCycleDiagnostics ?? [],
    },
    trend: overrides.trend === undefined ? null : overrides.trend,
  }
}

describe('parseExecutiveDashboard — diagnostics', () => {
  it('faz o parse de diagnostics[] do ciclo atual e da tendência', () => {
    const payload = buildExecutivePayload({
      currentCycleDiagnostics: [
        {
          code: 'IMPORTED_ENERGY_HIGH',
          severity: 'WARNING',
          message: 'Energia importada acima do esperado',
          recommended_action: 'Revisar consumo importado',
        },
      ],
      trend: {
        current_reference_month: '2026-07',
        previous_reference_month: '2026-06',
        metrics: {
          production: { absolute_delta: 10, percent_delta: 2, direction: 'UP' },
          total_consumption: { absolute_delta: 5, percent_delta: 1, direction: 'UP' },
          imported_energy: { absolute_delta: -3, percent_delta: -2, direction: 'DOWN' },
          self_sufficiency_delta_points: 1.5,
          health_score_delta: -5,
        },
        diagnostics: [
          {
            code: 'HEALTH_SCORE_DROPPED',
            severity: 'CRITICAL',
            message: 'Índice de saúde caiu em relação ao ciclo anterior',
            recommended_action: 'Investigar queda de desempenho',
          },
        ],
      },
    })

    const result = parseExecutiveDashboard(payload)

    expect(result.current_cycle.diagnostics).toHaveLength(1)
    expect(result.current_cycle.diagnostics[0].code).toBe('IMPORTED_ENERGY_HIGH')
    expect(result.trend?.diagnostics).toHaveLength(1)
    expect(result.trend?.diagnostics[0].severity).toBe('CRITICAL')
  })

  it('rejeita severidade fora do vocabulário conhecido', () => {
    const payload = buildExecutivePayload({
      currentCycleDiagnostics: [
        {
          code: 'X',
          severity: 'UNKNOWN',
          message: 'msg',
          recommended_action: 'ação',
        },
      ],
    })

    expect(() => parseExecutiveDashboard(payload)).toThrow()
  })
})

function buildAnomalyPayload(overrides: Record<string, unknown> = {}): unknown {
  return {
    plant_id: 'plant-1',
    days_analyzed: 2,
    current_streak_days: 0,
    worst_level: 'ATTENTION',
    expected_unavailable_reason: null,
    period_yield_kwh_per_kwh_m2: null,
    yield_atypical_threshold_percent: '20',
    period_yield_sample_days: 0,
    daily: [buildDaily()],
    ...overrides,
  }
}

describe('parseAnomalyDashboard — contrato novo (200 sempre, campos por dia nulos sem expectativa)', () => {
  it('aceita level: null em um dia sem expectativa disponível, sem lançar erro', () => {
    const payload = buildAnomalyPayload({
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
          diagnostics: [],
        },
      ],
    })

    const result = parseAnomalyDashboard(payload)

    expect(result.daily[0].level).toBeNull()
    expect(result.daily[0].expected_production_kwh).toBeNull()
    expect(result.daily[0].actual_production_kwh).toBe(40)
  })

  it('aceita worst_level: null quando nenhum dia teve expectativa avaliável', () => {
    const payload = buildAnomalyPayload({ worst_level: null })

    const result = parseAnomalyDashboard(payload)

    expect(result.worst_level).toBeNull()
  })

  it('aceita expected_unavailable_reason presente (string) e ausente (chave omitida)', () => {
    const withReason = parseAnomalyDashboard(
      buildAnomalyPayload({ expected_unavailable_reason: 'REFERENCE_YEAR_INCOMPLETE' })
    )
    expect(withReason.expected_unavailable_reason).toBe('REFERENCE_YEAR_INCOMPLETE')

    const payloadWithoutKey = buildAnomalyPayload()
    delete (payloadWithoutKey as Record<string, unknown>).expected_unavailable_reason
    const withoutKey = parseAnomalyDashboard(payloadWithoutKey)
    expect(withoutKey.expected_unavailable_reason).toBeNull()
  })

  it('ainda rejeita level fora do vocabulário conhecido (nem null, nem um AnomalyLevel válido)', () => {
    const payload = buildAnomalyPayload({
      daily: [{ ...buildDaily(), level: 'UNKNOWN_LEVEL' }],
    })

    expect(() => parseAnomalyDashboard(payload)).toThrow()
  })

  it('faz o parse de period_yield_sample_days separado de days_analyzed (plano T7b, P1)', () => {
    const payload = buildAnomalyPayload({ days_analyzed: 4, period_yield_sample_days: 2 })

    const result = parseAnomalyDashboard(payload)

    expect(result.days_analyzed).toBe(4)
    expect(result.period_yield_sample_days).toBe(2)
  })

  // Compatibilidade com backend uma versão atrás. Este teste afirmava o
  // oposto — que a ausência do campo era payload malformado. A premissa estava
  // errada e teria derrubado o painel em produção: o deploy do frontend chega
  // antes do backend, a API responde sem os campos de rendimento, e
  // `parseAnomalyDashboard` lançaria em TODA resposta — quebrando a
  // `ProductionPage` inteira e o indicador principal da Visão Geral, não só os
  // cards novos. Chave ausente é servidor desatualizado (estado legítimo, vira
  // indisponibilidade); valor com tipo errado continua sendo contrato violado.
  it('aceita payload de backend antigo, sem os campos de rendimento, sem derrubar a tela', () => {
    const payload = buildAnomalyPayload() as Record<string, unknown>
    delete payload.period_yield_sample_days
    delete payload.period_yield_kwh_per_kwh_m2
    delete payload.yield_atypical_threshold_percent
    for (const day of payload.daily as Record<string, unknown>[]) {
      delete day.yield_kwh_per_kwh_m2
      delete day.yield_deviation_from_median_percent
    }

    const result = parseAnomalyDashboard(payload)

    expect(result.period_yield_kwh_per_kwh_m2).toBeNull()
    expect(result.yield_atypical_threshold_percent).toBeNull()
    expect(result.period_yield_sample_days).toBe(0)
    expect(result.daily[0].yield_kwh_per_kwh_m2).toBeNull()
    expect(result.daily[0].yield_deviation_from_median_percent).toBeNull()
    // O resto do payload continua parseado normalmente — é isso que mantém a
    // página de pé enquanto o backend não sobe.
    expect(result.days_analyzed).toBe(payload.days_analyzed)
    expect(result.daily.length).toBeGreaterThan(0)
    expect(result.daily[0].date).toBeTruthy()
  })

  // A tolerância acima não pode virar leniência geral: presente com tipo
  // errado segue sendo erro de contrato.
  it('continua rejeitando campo de rendimento presente com tipo inválido', () => {
    const payload = buildAnomalyPayload() as Record<string, unknown>
    payload.period_yield_sample_days = 'dois'

    expect(() => parseAnomalyDashboard(payload)).toThrow()
  })
})

// Plano T7b, P2 ("dados servidos e descartados"): `period.start_date`/
// `end_date` chegam do backend desde a origem deste endpoint
// (`intelligence/router.py::_serialize_anomalies`) mas eram descartados
// inteiros pelo parser. Três casos obrigatórios (§2.2): payload válido,
// campo ausente/indisponível, payload malformado.
describe('parseAnomalyDashboard — period (plano T7b, P2)', () => {
  it('faz o parse de period.start_date/end_date quando presente', () => {
    const payload = buildAnomalyPayload({
      period: { start_date: '2026-07-01', end_date: '2026-07-30' },
    })

    const result = parseAnomalyDashboard(payload)

    expect(result.period).toEqual({ start_date: '2026-07-01', end_date: '2026-07-30' })
  })

  it('aceita period ausente (backend uma versão atrás) sem derrubar o parse — vira null', () => {
    const payload = buildAnomalyPayload() as Record<string, unknown>
    delete payload.period

    const result = parseAnomalyDashboard(payload)

    expect(result.period).toBeNull()
  })

  it('rejeita period presente com forma inválida (falta end_date)', () => {
    const payload = buildAnomalyPayload({
      period: { start_date: '2026-07-01' },
    })

    expect(() => parseAnomalyDashboard(payload)).toThrow()
  })
})

// Plano T7b, P2: `temperature_mean_c` é coletado (`climate/open_meteo.py`) e
// persistido (`climate/db_models.py`) há tempo, mas nunca chegava ao
// contrato do frontend. Mesmos três casos obrigatórios, agora por dia.
describe('parseAnomalyDaily — temperature_mean_c (plano T7b, P2)', () => {
  it('faz o parse de temperature_mean_c quando presente', () => {
    const result = parseAnomalyDaily({ ...buildDaily(), temperature_mean_c: '31.50' })

    expect(result.temperature_mean_c).toBe('31.50')
  })

  it('aceita temperature_mean_c ausente (backend uma versão atrás) sem lançar — vira null', () => {
    const payload = buildDaily() as unknown as Record<string, unknown>
    delete payload.temperature_mean_c

    const result = parseAnomalyDaily(payload)

    expect(result.temperature_mean_c).toBeNull()
  })

  it('rejeita temperature_mean_c presente com tipo inválido', () => {
    const payload = { ...buildDaily(), temperature_mean_c: { value: 31.5 } }

    expect(() => parseAnomalyDaily(payload)).toThrow()
  })
})

describe('combineDiagnostics', () => {
  it('ordena por gravidade, mais crítico primeiro, combinando ciclo atual e tendência', () => {
    const dashboard: ExecutiveDashboardResponse = {
      plant_id: 'plant-1',
      status: 'CRITICAL',
      headline: 'headline',
      priority_actions: [],
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
        diagnostics: [
          { code: 'INFO_ONE', severity: 'INFO', message: 'info', recommended_action: 'ação info' },
          { code: 'WARN_ONE', severity: 'WARNING', message: 'warning', recommended_action: 'ação warning' },
        ],
      },
      trend: {
        current_reference_month: '2026-07',
        previous_reference_month: '2026-06',
        metrics: {
          production: { absolute_delta: 10, percent_delta: 2, direction: 'UP' },
          total_consumption: { absolute_delta: 5, percent_delta: 1, direction: 'UP' },
          imported_energy: { absolute_delta: -3, percent_delta: -2, direction: 'DOWN' },
          self_sufficiency_delta_points: 1.5,
          health_score_delta: -5,
        },
        diagnostics: [
          { code: 'CRIT_ONE', severity: 'CRITICAL', message: 'crítico', recommended_action: 'ação crítica' },
        ],
      },
    }

    const combined = combineDiagnostics(dashboard)

    expect(combined.map((item) => item.code)).toEqual(['CRIT_ONE', 'WARN_ONE', 'INFO_ONE'])
  })
})
