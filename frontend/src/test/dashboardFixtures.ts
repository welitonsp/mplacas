// Fixtures de teste compartilhadas entre `DashboardPage.test.tsx` (a suíte
// legada, ainda cobrindo a rota de Visão Geral não migrada) e os testes dos
// módulos já extraídos dela (ADR-072, Etapas 2-4). Cada etapa de migração move
// para cá só o mock do recurso que o módulo correspondente realmente passa a
// usar — nada é adicionado por antecipação para um recurso que nenhum módulo
// migrado ainda consome (`/photovoltaic/summary` para o módulo Técnico, Etapa 2;
// `/energy/executive/latest` e `/energy/financial-return/latest` para o módulo
// Financeiro, Etapa 3; `/energy/anomalies/latest` e
// `/reports/monthly/history` para o módulo Produção, Etapa 4).

// Constrói uma `Response` JSON — mesmo helper usado por todo ponto de mock de
// `../lib/api` na suíte (`DashboardPage.test.tsx` e os testes de módulo).
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// Usina única — resposta default de `fetchPlants` para todo teste que não é
// especificamente sobre seleção/múltiplas usinas (`PlantContext` busca
// `/plants` ao montar, ADR-069).
export const singlePlant = {
  id: '00000000-0000-0000-0000-000000000000',
  name: 'Usina de teste',
  installedPowerKwp: null,
}

// Resposta de exemplo para `GET /photovoltaic/summary` com os três blocos
// (performance, baseline, losses) presentes — usada pelo módulo Técnico
// (`TechnicalPage.test.tsx`, ADR-072 Etapa 2) e ainda por
// `DashboardPage.test.tsx`, que continua dependendo deste recurso para
// `expectedProduction` (consumido por `ProductionHistorySection`, dentro do
// módulo Produção, que só migra na Etapa 4).
export const photovoltaicSummaryPayload = {
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

// Resposta de exemplo para `GET /devices/daily-status` (ADR-074, Decisão 3) —
// usada pelo módulo Técnico (`TechnicalPage.test.tsx`, ADR-074 T1c). Dois
// inversores: um reportando com queda de rendimento (DROPPED), outro
// silencioso (`reporting_status: "NOT_REPORTED"`) — exercita simultaneamente
// a Restrição 1 do ADR (o inversor mudo nunca some da resposta) e a "armadilha
// obrigatória" da Decisão 3 (`yield_status` nunca deriva de `dropped` sozinho).
export const deviceDailyStatusPayload = {
  plant_id: 'plant-1',
  observation_date: '2026-08-11',
  observation_date_unavailable_reason: null,
  irradiation_kwh_m2: '4.890',
  irradiation_unavailable_reason: null,
  device_count: 2,
  reporting_device_count: 1,
  device_normal_threshold: '0.85',
  units: {
    production: 'kWh',
    irradiation: 'kWh/m2',
    rendimento: 'kWh/(kWh/m2)',
    relative_to_own_median: 'ratio',
    relative_to_own_median_deviation: 'percent',
  },
  devices: [
    {
      device_id: '11111111-1111-1111-1111-111111111111',
      serial_number: 'SN-1234567890',
      reporting_status: 'REPORTED',
      production_kwh: '12.500',
      last_reported_date: '2026-08-11',
      rendimento: '2.437',
      rendimento_median: '3.390',
      relative_to_own_median: '0.719',
      relative_to_own_median_deviation_percent: '-28.1',
      yield_status: 'DROPPED',
      yield_unavailable_reason: null,
    },
    {
      device_id: '22222222-2222-2222-2222-222222222222',
      serial_number: 'SN-0987654321',
      reporting_status: 'NOT_REPORTED',
      production_kwh: null,
      last_reported_date: '2026-07-28',
      rendimento: null,
      rendimento_median: null,
      relative_to_own_median: null,
      relative_to_own_median_deviation_percent: null,
      yield_status: 'UNKNOWN',
      yield_unavailable_reason: 'NOT_REPORTED',
    },
  ],
}

// Resposta de exemplo para `GET /energy/executive/latest` — usada pelo módulo
// Financeiro (`FinancialPage.test.tsx`, ADR-072 Etapa 3), que precisa do
// recurso executivo inteiro (não só um endpoint financeiro dedicado) porque
// `FinancialSection` consome `current_cycle.indicators` (ver ADR seção 2).
// Mesmos valores de `DashboardPage.test.tsx::executivePayload` — os dois
// testam o mesmo contrato de resposta.
export const executivePayload = {
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

// Retorno do investimento indisponível (CAPEX nunca registrado) — resposta
// default de `GET /energy/financial-return/latest` para o módulo Financeiro.
// É justamente este estado (`unavailable_reason: 'INVESTMENT_NOT_REGISTERED'`)
// que faz `FinancialReturnSection` renderizar o formulário de cadastro de CAPEX
// (`CapexRegistrationForm`), exercitado pelo teste de submissão do módulo.
export const financialReturnUnavailablePayload = {
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

// Resposta de exemplo para `GET /energy/anomalies/latest` — usada pelo módulo
// Produção (`ProductionPage.test.tsx`, ADR-072 Etapa 4) e ainda por
// `DashboardPage.test.tsx`, que continua dependendo deste recurso só para
// `latestDataDate` (consumido pelo `HeroCard`). Dois dias, o mais recente
// (2026-07-30) com produção real abaixo do esperado (`ATTENTION`) — mesmos
// valores usados pelos dois arquivos de teste, que testam o mesmo contrato de
// resposta.
export const anomalyPayload = {
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

// `/photovoltaic/summary` sem baseline sazonal (usina nova: produção real já
// é coletada, mas o primeiro ano de referência ainda não fechou) — usada pelo
// módulo Produção para provar que a busca de anomalias não depende deste
// resultado (ver `ProductionPage.test.tsx`, testes "histórico de produção não
// depende mais do baseline sazonal").
export const fallbackPhotovoltaicSummaryPayload = {
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

// Histórico de produção por ciclo de faturamento (`GET /reports/monthly/history`,
// ver `lib/dashboard/monthly-history-contracts.ts`) — payload default de
// `fetchMonthlyProductionHistory` para o módulo Produção. 3 ciclos em ordem
// cronológica, o último com uma lacuna de telemetria (`missing_days: 3`) para
// exercitar o selo "dados parciais" no fluxo real do módulo.
export const monthlyHistoryPayload = {
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
