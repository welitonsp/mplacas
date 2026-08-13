// Parser do contrato de `GET /devices/daily-status` (ADR-074, Decisão 3) —
// estado operacional por inversor (device) da usina, para o dia mais recente
// com qualquer `DailyEnergy`. Arquivo separado dos demais contratos porque
// este payload tem identidade de equipamento (`device_id`/`serial_number`) e
// uma taxonomia de indisponibilidade de rendimento própria (3 motivos), que
// não se mistura com o vocabulário de `/photovoltaic/summary` nem de
// `/energy/*`.
//
// Nenhum cálculo acontece aqui (ADR-074, Restrição 7 / regra 6 da tarefa):
// `relative_to_own_median`, `relative_to_own_median_deviation_percent`,
// `yield_status` e `device_normal_threshold` já vêm prontos do backend — este
// parser só valida forma e converte string→tipo, nunca soma/divide/compara
// valores entre si. Correção de rota (revisão P1 de T1c, 2026-08-12): este
// arquivo chegou a computar `(razão − 1) × 100` em `relativeToMedianPercent`
// (removida) — deslocar o ponto de referência do zero é cálculo de domínio,
// não conversão de unidade; ver `no-client-computed-relative-to-own-median-
// deviation.test.ts` para a guarda que protege esta regra.

export type ReportingStatus = 'REPORTED' | 'NOT_REPORTED'

const REPORTING_STATUSES: ReadonlySet<string> = new Set(['REPORTED', 'NOT_REPORTED'])

export type YieldStatus = 'NORMAL' | 'DROPPED' | 'UNKNOWN'

const YIELD_STATUSES: ReadonlySet<string> = new Set(['NORMAL', 'DROPPED', 'UNKNOWN'])

// Os três motivos mutuamente exclusivos da taxonomia (ADR-074, Decisão 3,
// tabela "Taxonomia de indisponibilidade") — só legítimo quando
// `yield_status === 'UNKNOWN'`.
export type YieldUnavailableReason =
  | 'NOT_REPORTED'
  | 'NO_IRRADIATION_READING'
  | 'INSUFFICIENT_DEVICE_HISTORY'

const YIELD_UNAVAILABLE_REASONS: ReadonlySet<string> = new Set([
  'NOT_REPORTED',
  'NO_IRRADIATION_READING',
  'INSUFFICIENT_DEVICE_HISTORY',
])

export type ObservationDateUnavailableReason = 'NO_PRODUCTION_HISTORY'

const OBSERVATION_DATE_UNAVAILABLE_REASONS: ReadonlySet<string> = new Set([
  'NO_PRODUCTION_HISTORY',
])

export type IrradiationUnavailableReason = 'NO_CLIMATE_OBSERVATION'

const IRRADIATION_UNAVAILABLE_REASONS: ReadonlySet<string> = new Set(['NO_CLIMATE_OBSERVATION'])

// Identificado por `serial_number` — nunca por posição na lista (ADR-074,
// Decisão 7: um ordinal inventado, tipo "Inversor 1", reordenaria sozinho ao
// cadastrar um terceiro device; o serial é a única identidade estável).
export interface DeviceDailyStatus {
  device_id: string
  serial_number: string
  reporting_status: ReportingStatus
  // `null` = não há linha `DailyEnergy` deste device no dia — nunca
  // confundir com `"0"` (device reportou zero, que é `REPORTED`).
  production_kwh: string | null
  // Data mais recente em que ESTE device já reportou algo, independente do
  // dia resolvido pelo envelope. `null` só quando o device nunca reportou.
  last_reported_date: string | null
  // kWh/(kWh/m²) — deliberadamente NÃO exibido bruto na tela (ADR-074,
  // Decisão 5, regra 3): é uma área sem significado físico direto para o
  // usuário, e a página já usa "rendimento" com outra unidade em
  // `SpecificYieldCard`. Mantido no contrato por completude do payload.
  rendimento: string | null
  rendimento_median: string | null
  // Razão contra a PRÓPRIA mediana histórica deste device — nunca comparado
  // entre devices (ADR-074, Restrição 2).
  relative_to_own_median: string | null
  // Desvio percentual pronto, `(relative_to_own_median − 1) × 100` — já
  // calculado pelo backend (`devices/metrics.py::assess_devices`), nunca
  // recomputado aqui. Correção de rota (revisão P1 de T1c, 2026-08-12): este
  // campo substitui a antiga `relativeToMedianPercent` deste arquivo, que
  // deslocava o ponto de referência do zero (razão menos um) — cálculo de
  // domínio, não conversão de unidade (ver `ratioToPercent` em
  // `photovoltaic-contracts.ts` para o precedente legítimo de reescala pura).
  // `null` sob a mesma condição de `relative_to_own_median` — nunca inventado
  // independentemente.
  relative_to_own_median_deviation_percent: string | null
  yield_status: YieldStatus
  yield_unavailable_reason: YieldUnavailableReason | null
}

export interface DeviceDailyStatusUnits {
  production: string
  irradiation: string
  rendimento: string
  relative_to_own_median: string
  relative_to_own_median_deviation: string
}

export interface DeviceDailyStatusResponse {
  plant_id: string
  // Dia mais recente com qualquer `DailyEnergy` da usina — `null` quando a
  // usina nunca teve nenhuma linha de produção (`observation_date_unavailable_reason`
  // explica por quê; `devices[]` ainda lista os inversores cadastrados).
  observation_date: string | null
  observation_date_unavailable_reason: ObservationDateUnavailableReason | null
  irradiation_kwh_m2: string | null
  irradiation_unavailable_reason: IrradiationUnavailableReason | null
  device_count: number
  reporting_device_count: number
  device_normal_threshold: string
  units: DeviceDailyStatusUnits
  devices: DeviceDailyStatus[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireString(source: Record<string, unknown>, key: string): string {
  const value = source[key]
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value
}

function nullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function numberValue(source: Record<string, unknown>, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

// Campo obrigatório de vocabulário fechado: um valor fora do conjunto
// conhecido é payload malformado, não um motivo novo a tolerar em silêncio.
// Diferente dos parsers de `*_unavailable_reason` abaixo, `reporting_status`
// e `yield_status` decidem diretamente se um device aparece como "reportou"
// e se o rendimento dele pode ser mostrado como saudável — um valor
// desconhecido aqui nunca deve degradar para um estado aparentemente normal
// (mesmo princípio de `contracts.ts::optionalAnomalyLevel`, que lança para um
// `AnomalyLevel` desconhecido em vez de escolher um default).
function requireEnum<T extends string>(
  source: Record<string, unknown>,
  key: string,
  allowed: ReadonlySet<string>
): T {
  const value = source[key]
  if (typeof value !== 'string' || !allowed.has(value)) {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value as T
}

// Motivo desconhecido vira `null` em vez de lançar — mesmo princípio
// defensivo de `photovoltaic-contracts.ts::parseBaselineUnavailableReason`:
// um backend mais novo pode adicionar um quarto motivo sem quebrar este
// cliente. A tela cai para uma frase genérica de "sem avaliação" nesse caso
// — `yield_status` (validado à parte, de forma estrita) continua garantindo
// que isso nunca vire "saudável".
function nullableYieldUnavailableReason(value: unknown): YieldUnavailableReason | null {
  if (typeof value === 'string' && YIELD_UNAVAILABLE_REASONS.has(value)) {
    return value as YieldUnavailableReason
  }
  return null
}

function nullableObservationDateUnavailableReason(
  value: unknown
): ObservationDateUnavailableReason | null {
  if (typeof value === 'string' && OBSERVATION_DATE_UNAVAILABLE_REASONS.has(value)) {
    return value as ObservationDateUnavailableReason
  }
  return null
}

function nullableIrradiationUnavailableReason(value: unknown): IrradiationUnavailableReason | null {
  if (typeof value === 'string' && IRRADIATION_UNAVAILABLE_REASONS.has(value)) {
    return value as IrradiationUnavailableReason
  }
  return null
}

function parseUnits(value: unknown): DeviceDailyStatusUnits {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: units')
  return {
    production: requireString(value, 'production'),
    irradiation: requireString(value, 'irradiation'),
    rendimento: requireString(value, 'rendimento'),
    relative_to_own_median: requireString(value, 'relative_to_own_median'),
    relative_to_own_median_deviation: requireString(value, 'relative_to_own_median_deviation'),
  }
}

function parseDeviceStatus(value: unknown): DeviceDailyStatus {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: devices[]')
  return {
    device_id: requireString(value, 'device_id'),
    serial_number: requireString(value, 'serial_number'),
    reporting_status: requireEnum<ReportingStatus>(value, 'reporting_status', REPORTING_STATUSES),
    production_kwh: nullableString(value, 'production_kwh'),
    last_reported_date: nullableString(value, 'last_reported_date'),
    rendimento: nullableString(value, 'rendimento'),
    rendimento_median: nullableString(value, 'rendimento_median'),
    relative_to_own_median: nullableString(value, 'relative_to_own_median'),
    relative_to_own_median_deviation_percent: nullableString(
      value,
      'relative_to_own_median_deviation_percent'
    ),
    yield_status: requireEnum<YieldStatus>(value, 'yield_status', YIELD_STATUSES),
    yield_unavailable_reason: nullableYieldUnavailableReason(value.yield_unavailable_reason),
  }
}

export function parseDeviceDailyStatus(payload: unknown): DeviceDailyStatusResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const devices = payload.devices
  if (!Array.isArray(devices)) throw new Error('Resposta inválida da API: devices')
  return {
    plant_id: requireString(payload, 'plant_id'),
    observation_date: nullableString(payload, 'observation_date'),
    observation_date_unavailable_reason: nullableObservationDateUnavailableReason(
      payload.observation_date_unavailable_reason
    ),
    irradiation_kwh_m2: nullableString(payload, 'irradiation_kwh_m2'),
    irradiation_unavailable_reason: nullableIrradiationUnavailableReason(
      payload.irradiation_unavailable_reason
    ),
    device_count: numberValue(payload, 'device_count'),
    reporting_device_count: numberValue(payload, 'reporting_device_count'),
    device_normal_threshold: requireString(payload, 'device_normal_threshold'),
    units: parseUnits(payload.units),
    devices: devices.map(parseDeviceStatus),
  }
}

// Mensagem própria por motivo (ADR-074, Decisão 5, regra 4) — nunca um "—"
// genérico. Só chamada para os dois motivos que podem ocorrer com
// `reporting_status: 'REPORTED'` (o device enviou dado, mas o rendimento não
// pôde ser avaliado); o motivo `NOT_REPORTED` tem tela própria no componente,
// que já comunica "não reportou" através de `reporting_status` e
// `last_reported_date`, mais informativo do que repetir esta frase genérica.
export function yieldUnavailableMessage(reason: YieldUnavailableReason): string {
  switch (reason) {
    case 'NOT_REPORTED':
      return 'Não reportou neste dia.'
    case 'NO_IRRADIATION_READING':
      return 'Sem leitura de irradiação neste dia.'
    case 'INSUFFICIENT_DEVICE_HISTORY':
      return 'Histórico insuficiente para comparar (mínimo 5 dias).'
  }
}

export function observationDateUnavailableMessage(
  _reason: ObservationDateUnavailableReason
): string {
  return 'Nenhum dia com produção registrada ainda para esta usina.'
}
