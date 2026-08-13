export type MetricValue = string | number | null
export type Severity = 'success' | 'warning' | 'danger' | 'neutral'

export interface CycleQuality {
  missing_days: number
  provisional_days: number
  incomplete_days: number
  unavailable_days: number
}

export interface ExecutiveIndicators {
  cycle_production_kwh: MetricValue
  imported_kwh: MetricValue
  injected_kwh: MetricValue
  estimated_self_consumption_kwh: MetricValue
  estimated_total_consumption_kwh: MetricValue
  self_consumption_rate_percent: MetricValue
  self_sufficiency_rate_percent: MetricValue
  grid_dependency_rate_percent: MetricValue
  exported_generation_rate_percent: MetricValue
  credit_coverage_rate_percent: MetricValue
  bill_energy_component_brl: MetricValue
  health_score: MetricValue
  total_amount_brl: MetricValue
  public_lighting_brl: MetricValue
  tariff_with_taxes_brl_kwh: MetricValue
  tariff_without_taxes_brl_kwh: MetricValue
  credit_balance_kwh: MetricValue
  // `null` quando a fatura do ciclo não tem tarifa registrada — nunca um R$
  // 0,00 fabricado nesse caso. Ver `savings_unavailable_reason` para o motivo
  // explícito (ver intelligence/energy_engine.py::analyze_energy_cycle).
  estimated_savings_brl: MetricValue
  savings_unavailable_reason: string | null
}

// Vocabulário compartilhado com o backend (ver
// intelligence/energy_engine.py::SAVINGS_UNAVAILABLE_TARIFF_NOT_REGISTERED)
// — hoje o único motivo possível é a fatura do ciclo não ter tarifa com
// impostos registrada. Nunca renderizar R$ 0,00 quando este campo vem
// preenchido; mostrar a mensagem explícita abaixo no lugar do valor.
export function savingsUnavailableMessage(reason: string): string {
  switch (reason) {
    case 'TARIFF_NOT_AVAILABLE':
      return 'Economia estimada ainda não disponível — a fatura deste ciclo não tem a tarifa com impostos registrada.'
    case 'NO_CONSUMPTION_DATA':
      return 'Economia estimada ainda não disponível — ainda não há dado de consumo para este ciclo.'
    default:
      return 'Economia estimada ainda não disponível para este ciclo.'
  }
}

// Vocabulário compartilhado com o backend (ver intelligence/energy_engine.py::DiagnosticSeverity).
export type DiagnosticSeverity = 'CRITICAL' | 'WARNING' | 'INFO'
export const DIAGNOSTIC_SEVERITIES: ReadonlySet<string> = new Set(['CRITICAL', 'WARNING', 'INFO'])

// Um diagnóstico é o "porquê" por trás de uma ação prioritária: problema detectado
// (`message`), gravidade (`severity`) e o que fazer a respeito (`recommended_action`).
// `priority_actions` no payload é só a lista deduplicada de `recommended_action` de
// todos os diagnósticos (ver intelligence/executive_service.py::_priority_actions) —
// por isso a UI deve mostrar o diagnóstico completo, não a ação isolada.
export interface Diagnostic {
  code: string
  severity: DiagnosticSeverity
  message: string
  recommended_action: string
}

export interface ExecutiveCycle {
  reference_month: string
  quality: CycleQuality
  indicators: ExecutiveIndicators
  diagnostics: Diagnostic[]
}

export type TrendDirection = 'UP' | 'DOWN' | 'STABLE'

export interface TrendMetric {
  absolute_delta: MetricValue
  percent_delta: MetricValue
  direction: TrendDirection
}

export interface TrendMetrics {
  production: TrendMetric
  total_consumption: TrendMetric
  imported_energy: TrendMetric
  self_sufficiency_delta_points: MetricValue
  health_score_delta: MetricValue
}

export interface ExecutiveTrend {
  current_reference_month: string
  previous_reference_month: string
  metrics: TrendMetrics
  diagnostics: Diagnostic[]
}

export interface ExecutiveDashboardResponse {
  plant_id: string
  status: string
  headline: string
  priority_actions: string[]
  current_cycle: ExecutiveCycle
  trend: ExecutiveTrend | null
}

// Vocabulário compartilhado com o backend (ver intelligence/anomaly_engine.py::AnomalyLevel).
export type AnomalyLevel = 'NORMAL' | 'ATTENTION' | 'ANOMALY' | 'CRITICAL'
export const ANOMALY_LEVELS: ReadonlySet<string> = new Set(['NORMAL', 'ATTENTION', 'ANOMALY', 'CRITICAL'])

// Diagnóstico por dia dentro de `AnomalyDailyPoint.diagnostics` (ADR-075,
// Decisão 4.1) — motor determinístico, mesmo objeto que já alimenta o
// alerta de anomalia por Telegram (`alerts/candidates.py`). Vocabulário
// próprio: aqui é `level` (reusa `AnomalyLevel`/`ANOMALY_LEVELS` acima),
// nunca `severity`/`DiagnosticSeverity` do executivo — as duas taxonomias
// não se misturam (ver `intelligence/router.py::latest_energy_anomalies`,
// `:200-208`, e `intelligence/anomaly_engine.py:134-241` para os 6 códigos
// possíveis).
export interface AnomalyDiagnostic {
  code: string
  level: AnomalyLevel
  message: string
  recommended_action: string
}

export interface AnomalyDailyPoint {
  date: string
  actual_production_kwh: MetricValue
  expected_production_kwh: MetricValue
  // `null` quando não há expectativa disponível pra calcular severidade nesse
  // dia (ex.: usina sem baseline sazonal ainda) — estado legítimo, distinto de
  // campo malformado. Nunca fabricar um nível a partir de um dia sem
  // expectativa (ver `intelligence/anomaly_service.py::analyze_recent_persisted_anomalies`).
  level: AnomalyLevel | null
  // Diagnósticos do dia — hoje sempre 0 ou 1 item (`assessment.diagnostics`
  // é uma tupla de um elemento em todo ramo de `assess_daily_performance`,
  // `anomaly_engine.py:134-241`), mas tratado como lista porque é o que o
  // payload manda. `[]` quando o dia não tem assessment (`level: null`) —
  // mesmo caso, não um erro. Fonte de `episodes.ts::buildAnomalyEpisodes`
  // (ADR-075, Decisão 4.2): agrupa dias consecutivos com o mesmo `code` numa
  // linha do tempo, sem inventar nenhum dado novo.
  diagnostics: AnomalyDiagnostic[]
  deviation_percent: MetricValue
  // Preenchido só quando a usina tem coordenadas configuradas (coleta Open-Meteo
  // ativa). Em qualquer organização nova vem `null` — todo consumidor deste campo
  // precisa tratar ausência sem quebrar (ver YieldCard e overlay de irradiância).
  irradiation_kwh_m2: MetricValue
  // production_kwh / irradiation_kwh_m2 deste dia, já pronto do backend
  // (`intelligence/anomaly_service.py::_compute_period_yield`). `null` só
  // quando não há irradiância positiva nesse dia (sem denominador, sem
  // razão possível). Um dia com produção zero SOB irradiância positiva vem
  // como `0` — real, não fabricado: é a razão perfeitamente definida do
  // pior evento de rendimento possível (apagão sob sol), e precisa
  // continuar aparecendo, não sumir como se não houvesse dado (plano T7b,
  // P1 "dia de produção zero com sol desaparece"). Ver
  // `no-client-computed-yield-deviation.test.ts` para a guarda estática que
  // impede recomputar isto no cliente.
  yield_kwh_per_kwh_m2: MetricValue
  // Desvio percentual deste dia em relação ao rendimento agregado do período
  // (`AnomalyDashboardResponse.period_yield_kwh_per_kwh_m2`), pronto do
  // backend — `((yield_kwh_per_kwh_m2 / period_yield) − 1) × 100`. `null` sob
  // a mesma condição de `yield_kwh_per_kwh_m2`, ou quando o rendimento do
  // período inteiro também é `null`. Movido do antigo
  // `lib/dashboard/yield.ts` (arquivo removido, 2026-08-13, plano T7):
  // deslocar o ponto de referência do zero é cálculo de domínio, não
  // conversão de unidade — mesma razão de
  // `device-contracts.ts::relative_to_own_median_deviation_percent`.
  yield_deviation_from_period_percent: MetricValue
}

export interface AnomalyDashboardResponse {
  plant_id: string
  days_analyzed: number
  current_streak_days: number
  // `null` quando nenhum dia do período teve expectativa disponível pra
  // calcular severidade (ver `expected_unavailable_reason` abaixo) — não é o
  // mesmo caso de "sem dado nenhum" (esse continua sendo 404, ver
  // `AnomalyFetchError`).
  worst_level: AnomalyLevel | null
  // Motivo pelo qual a produção esperada não está disponível pra este
  // período (mesmo vocabulário de `BaselineUnavailableReason`, ver
  // `photovoltaic-contracts.ts` — `resolve_expected_daily_production` reusa
  // `_derive_baseline_unavailable_reason` no backend). `null` = expectativa
  // disponível.
  expected_unavailable_reason: string | null
  // Rendimento agregado do período (produção total ÷ irradiância total dos
  // dias com ambos disponíveis) — `null` quando nenhum dia do recorte
  // qualifica. Ver comentário de `AnomalyDailyPoint.yield_kwh_per_kwh_m2`
  // para a fórmula e a distinção em relação à mediana histórica por
  // inversor (`device-contracts.ts::rendimento_median`).
  period_yield_kwh_per_kwh_m2: MetricValue
  // Limiar fixo de severidade (%) que marca um dia como "rendimento
  // atípico" em relação ao rendimento do período — sempre presente, mesmo
  // quando `period_yield_kwh_per_kwh_m2` é `null` (é política, não dado
  // derivado; mesmo padrão de `device-contracts.ts::device_normal_threshold`).
  yield_atypical_threshold_percent: MetricValue
  // Quantos dias de `daily` realmente alimentaram `period_yield_kwh_per_kwh_m2`
  // (produção E irradiância positivas nesse dia) — deliberadamente
  // DIFERENTE de `days_analyzed` (todo dia com linha de produção
  // persistida, mesmo sem irradiância). Rotular o rendimento do período com
  // `days_analyzed` afirma ter varrido dias que na verdade não entraram na
  // conta (plano T7b, P1 "o rótulo usa a contagem errada" —
  // `intelligence/anomaly_service.py::PersistedAnomalySummary.
  // period_yield_sample_days`). `YieldCard` deve rotular com este campo,
  // nunca com `days_analyzed`.
  period_yield_sample_days: number
  daily: AnomalyDailyPoint[]
}

export interface FetchState {
  data: ExecutiveDashboardResponse | null
  loading: boolean
  error: string | null
  lastUpdated: Date | null
}

// `NOT_FOUND` = ainda não há dado diário coletado para o período pedido (404 —
// não é uma falha do sistema, é um estado esperado para usina nova/sem backfill).
// `SERVER_ERROR` = 5xx ou falha de rede — aí sim algo quebrou e vale oferecer retry.
export type AnomalyFetchError = 'NOT_FOUND' | 'SERVER_ERROR'

export interface AnomalyFetchState {
  data: AnomalyDashboardResponse | null
  loading: boolean
  error: AnomalyFetchError | null
}

// Classifica o status HTTP de `/energy/anomalies/latest` em uma mensagem de estado
// distinta — nunca trata 404 (sem dado ainda) e 5xx/rede (algo quebrou) como a
// mesma coisa. 401 retorna `null` porque `apiFetch` já tentou refresh e, se ainda
// assim falhou, o usuário está sendo deslogado (não é um estado a comunicar aqui).
export function classifyAnomalyErrorStatus(status: number): AnomalyFetchError | null {
  if (status === 401) return null
  if (status === 404) return 'NOT_FOUND'
  return 'SERVER_ERROR'
}

// Mais crítico primeiro — mesma ordem de gravidade usada no backend para decidir o
// `status` executivo (ver intelligence/executive_service.py::_status_for_cycle).
const DIAGNOSTIC_SEVERITY_ORDER: Record<DiagnosticSeverity, number> = {
  CRITICAL: 0,
  WARNING: 1,
  INFO: 2,
}

// Combina os diagnósticos do ciclo atual com os da tendência (quando houver) e
// ordena por gravidade — a mesma lista de onde `priority_actions` é derivada no
// backend (ver intelligence/executive_service.py::_priority_actions), mas mantendo
// o problema e a severidade junto da ação, não só a ação isolada.
export function combineDiagnostics(dashboard: ExecutiveDashboardResponse): Diagnostic[] {
  const all = [...dashboard.current_cycle.diagnostics, ...(dashboard.trend?.diagnostics ?? [])]
  return [...all].sort(
    (a, b) => DIAGNOSTIC_SEVERITY_ORDER[a.severity] - DIAGNOSTIC_SEVERITY_ORDER[b.severity],
  )
}

// Data (ISO `YYYY-MM-DD`) do último dia com produção diária realmente coletada
// (`actual_production_kwh` não nulo) no payload de anomalias — usado para mostrar
// o frescor real do dado em vez da hora em que o navegador fez o fetch. `daily`
// vem em ordem cronológica ascendente (ver `intelligence/anomaly_service.py`).
export function latestNonNullProductionDate(daily: readonly AnomalyDailyPoint[]): string | null {
  for (let i = daily.length - 1; i >= 0; i -= 1) {
    if (daily[i].actual_production_kwh != null) return daily[i].date
  }
  return null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireRecord(source: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = source[key]
  if (!isRecord(value)) throw new Error(`Resposta inválida da API: ${key}`)
  return value
}

function requireString(source: Record<string, unknown>, key: string): string {
  const value = source[key]
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value
}

function optionalString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null) return null
  if (typeof value === 'string' && value.trim() !== '') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function metricValue(source: Record<string, unknown>, key: string): MetricValue {
  const value = source[key]
  if (value === null || typeof value === 'string' || typeof value === 'number') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function numberValue(source: Record<string, unknown>, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

// Compatibilidade com backend uma versão atrás — campos introduzidos depois de
// um deploy do frontend.
//
// A distinção que estas duas funções preservam é a que importa: **chave ausente
// não é a mesma coisa que valor malformado**. Ausente significa que o servidor
// ainda não conhece o campo (deploy do frontend chegou antes do backend, ou
// rollback do backend) — é estado legítimo e vira indisponibilidade explícita,
// que é como o projeto trata falta de dado em todo lugar. Presente com tipo
// errado continua lançando, porque aí o contrato foi de fato violado.
//
// Sem isso, um frontend novo contra um backend antigo derruba a página inteira
// em vez de esconder um card: `parseAnomalyDashboard` lançaria em toda resposta
// e `ProductionPage` pararia por completo. Mesmo princípio de
// `optionalStringOrMissing` logo abaixo.
function metricValueOrMissing(source: Record<string, unknown>, key: string): MetricValue {
  if (!(key in source) || source[key] === undefined) return null
  return metricValue(source, key)
}

function numberValueOrMissing(
  source: Record<string, unknown>,
  key: string,
  fallback: number
): number {
  if (!(key in source) || source[key] === undefined) return fallback
  return numberValue(source, key)
}

const TREND_DIRECTIONS: ReadonlySet<string> = new Set(['UP', 'DOWN', 'STABLE'])

function requireDirection(source: Record<string, unknown>, key: string): TrendDirection {
  const value = source[key]
  if (typeof value !== 'string' || !TREND_DIRECTIONS.has(value)) {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value as TrendDirection
}

function parseTrendMetric(source: Record<string, unknown>, key: string): TrendMetric {
  const metric = requireRecord(source, key)
  return {
    absolute_delta: metricValue(metric, 'absolute_delta'),
    percent_delta: metricValue(metric, 'percent_delta'),
    direction: requireDirection(metric, 'direction'),
  }
}

function requireDiagnosticSeverity(source: Record<string, unknown>, key: string): DiagnosticSeverity {
  const value = source[key]
  if (typeof value !== 'string' || !DIAGNOSTIC_SEVERITIES.has(value)) {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value as DiagnosticSeverity
}

function parseDiagnostic(value: unknown): Diagnostic {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: diagnostics')
  return {
    code: requireString(value, 'code'),
    severity: requireDiagnosticSeverity(value, 'severity'),
    message: requireString(value, 'message'),
    recommended_action: requireString(value, 'recommended_action'),
  }
}

function parseDiagnostics(source: Record<string, unknown>): Diagnostic[] {
  const diagnostics = source.diagnostics
  if (!Array.isArray(diagnostics)) throw new Error('Resposta inválida da API: diagnostics')
  return diagnostics.map(parseDiagnostic)
}

function optionalTrend(source: Record<string, unknown>): ExecutiveTrend | null {
  const trend = source.trend
  if (trend === null) return null
  if (!isRecord(trend)) throw new Error('Resposta inválida da API: trend')
  const metrics = requireRecord(trend, 'metrics')
  return {
    current_reference_month: requireString(trend, 'current_reference_month'),
    previous_reference_month: requireString(trend, 'previous_reference_month'),
    metrics: {
      production: parseTrendMetric(metrics, 'production'),
      total_consumption: parseTrendMetric(metrics, 'total_consumption'),
      imported_energy: parseTrendMetric(metrics, 'imported_energy'),
      self_sufficiency_delta_points: metricValue(metrics, 'self_sufficiency_delta_points'),
      health_score_delta: metricValue(metrics, 'health_score_delta'),
    },
    diagnostics: parseDiagnostics(trend),
  }
}

// Tolera a chave ausente (`undefined`) além de `null` — mesmo padrão de
// `photovoltaic-contracts.ts::optionalString`, usado aqui só para
// `expected_unavailable_reason` porque payloads de teste anteriores a este
// campo (e clientes antigos em cache) não o emitem; a chave ausente não deve
// ser tratada como resposta malformada.
function optionalStringOrMissing(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === undefined || value === null) return null
  if (typeof value === 'string' && value.trim() !== '') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

// `null` é um valor válido e explícito (sem expectativa pra calcular
// severidade nesse dia/período) — só valores fora do vocabulário conhecido
// (nem `null`, nem um `AnomalyLevel` válido) contam como campo malformado.
function optionalAnomalyLevel(source: Record<string, unknown>, key: string): AnomalyLevel | null {
  const value = source[key]
  if (value === null) return null
  if (typeof value !== 'string' || !ANOMALY_LEVELS.has(value)) {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value as AnomalyLevel
}

// Diferente de `parseDiagnostic`/`parseDiagnostics` (executivo, campo
// `severity`, lança em item malformado): esta validação é tolerante por
// item, não por chamador — ver `parseAnomalyDiagnostics` logo abaixo para o
// porquê (ADR-075, Decisão 4.1).
function isValidAnomalyDiagnostic(value: unknown): value is {
  code: string
  level: AnomalyLevel
  message: string
  recommended_action: string
} {
  if (!isRecord(value)) return false
  const { code, level, message, recommended_action } = value
  return (
    typeof code === 'string' &&
    code.trim() !== '' &&
    typeof level === 'string' &&
    ANOMALY_LEVELS.has(level) &&
    typeof message === 'string' &&
    message.trim() !== '' &&
    typeof recommended_action === 'string' &&
    recommended_action.trim() !== ''
  )
}

// `diagnostics` é um campo aditivo do dia (ADR-075, Decisão 4.1): ausente ou
// não-array vira `[]`, nunca lança — diferente de `daily`, que é estrutural
// (`parseAnomalyDashboard` continua exigindo o array). Um backend antigo, ou
// qualquer mudança aditiva futura no mesmo objeto, não pode derrubar a tela
// inteira por causa de um campo que o cliente só passou a ler agora. Item
// malformado dentro do array é descartado individualmente — o dia sobrevive,
// nunca se inventa `code`/`level`/`message`/`recommended_action` a partir de
// um item incompleto.
function parseAnomalyDiagnostics(source: Record<string, unknown>): AnomalyDiagnostic[] {
  const value = source.diagnostics
  if (!Array.isArray(value)) return []
  const diagnostics: AnomalyDiagnostic[] = []
  for (const item of value) {
    if (!isValidAnomalyDiagnostic(item)) continue
    diagnostics.push({
      code: item.code,
      level: item.level,
      message: item.message,
      recommended_action: item.recommended_action,
    })
  }
  return diagnostics
}

export function parseAnomalyDaily(value: unknown): AnomalyDailyPoint {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: daily')
  return {
    date: requireString(value, 'date'),
    actual_production_kwh: metricValue(value, 'actual_production_kwh'),
    expected_production_kwh: metricValue(value, 'expected_production_kwh'),
    level: optionalAnomalyLevel(value, 'level'),
    diagnostics: parseAnomalyDiagnostics(value),
    deviation_percent: metricValue(value, 'deviation_percent'),
    irradiation_kwh_m2: metricValue(value, 'irradiation_kwh_m2'),
    yield_kwh_per_kwh_m2: metricValueOrMissing(value, 'yield_kwh_per_kwh_m2'),
    yield_deviation_from_period_percent: metricValueOrMissing(value, 'yield_deviation_from_period_percent'),
  }
}

export function parseAnomalyDashboard(payload: unknown): AnomalyDashboardResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const daily = payload.daily
  if (!Array.isArray(daily)) throw new Error('Resposta inválida da API: daily')
  return {
    plant_id: requireString(payload, 'plant_id'),
    days_analyzed: numberValue(payload, 'days_analyzed'),
    current_streak_days: numberValue(payload, 'current_streak_days'),
    worst_level: optionalAnomalyLevel(payload, 'worst_level'),
    expected_unavailable_reason: optionalStringOrMissing(payload, 'expected_unavailable_reason'),
    period_yield_kwh_per_kwh_m2: metricValueOrMissing(payload, 'period_yield_kwh_per_kwh_m2'),
    yield_atypical_threshold_percent: metricValueOrMissing(payload, 'yield_atypical_threshold_percent'),
    period_yield_sample_days: numberValueOrMissing(payload, 'period_yield_sample_days', 0),
    daily: daily.map(parseAnomalyDaily),
  }
}

export function parseExecutiveDashboard(payload: unknown): ExecutiveDashboardResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')

  const currentCycle = requireRecord(payload, 'current_cycle')
  const quality = requireRecord(currentCycle, 'quality')
  const indicators = requireRecord(currentCycle, 'indicators')
  const priorityActions = payload.priority_actions

  if (!Array.isArray(priorityActions) || !priorityActions.every((item) => typeof item === 'string')) {
    throw new Error('Resposta inválida da API: priority_actions')
  }

  return {
    plant_id: requireString(payload, 'plant_id'),
    status: requireString(payload, 'status'),
    headline: requireString(payload, 'headline'),
    priority_actions: priorityActions,
    current_cycle: {
      reference_month: requireString(currentCycle, 'reference_month'),
      quality: {
        missing_days: numberValue(quality, 'missing_days'),
        provisional_days: numberValue(quality, 'provisional_days'),
        incomplete_days: numberValue(quality, 'incomplete_days'),
        unavailable_days: numberValue(quality, 'unavailable_days'),
      },
      indicators: {
        cycle_production_kwh: metricValue(indicators, 'cycle_production_kwh'),
        imported_kwh: metricValue(indicators, 'imported_kwh'),
        injected_kwh: metricValue(indicators, 'injected_kwh'),
        estimated_self_consumption_kwh: metricValue(indicators, 'estimated_self_consumption_kwh'),
        estimated_total_consumption_kwh: metricValue(indicators, 'estimated_total_consumption_kwh'),
        self_consumption_rate_percent: metricValue(indicators, 'self_consumption_rate_percent'),
        self_sufficiency_rate_percent: metricValue(indicators, 'self_sufficiency_rate_percent'),
        grid_dependency_rate_percent: metricValue(indicators, 'grid_dependency_rate_percent'),
        exported_generation_rate_percent: metricValue(indicators, 'exported_generation_rate_percent'),
        credit_coverage_rate_percent: metricValue(indicators, 'credit_coverage_rate_percent'),
        bill_energy_component_brl: metricValue(indicators, 'bill_energy_component_brl'),
        health_score: metricValue(indicators, 'health_score'),
        total_amount_brl: metricValue(indicators, 'total_amount_brl'),
        public_lighting_brl: metricValue(indicators, 'public_lighting_brl'),
        tariff_with_taxes_brl_kwh: metricValue(indicators, 'tariff_with_taxes_brl_kwh'),
        tariff_without_taxes_brl_kwh: metricValue(indicators, 'tariff_without_taxes_brl_kwh'),
        credit_balance_kwh: metricValue(indicators, 'credit_balance_kwh'),
        estimated_savings_brl: metricValue(indicators, 'estimated_savings_brl'),
        savings_unavailable_reason: optionalString(indicators, 'savings_unavailable_reason'),
      },
      diagnostics: parseDiagnostics(currentCycle),
    },
    trend: optionalTrend(payload),
  }
}
