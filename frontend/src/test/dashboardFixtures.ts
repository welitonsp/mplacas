// Fixtures de teste compartilhadas entre `DashboardPage.test.tsx` (a suíte
// legada, ainda cobrindo as 3 rotas de módulo não migradas) e os testes dos
// módulos já extraídos dela (ADR-072, Etapa 2). Cada etapa de migração move
// para cá só o mock do recurso que o módulo correspondente realmente passa a
// usar — nada é adicionado por antecipação para um recurso que nenhum módulo
// migrado ainda consome (ver ADR-072, Etapa 2: só `/photovoltaic/summary`,
// usado pelo módulo Técnico).

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
