// Parser de `GET /energy/expansion/latest` (ver `intelligence/router.py::
// _serialize_expansion`, ADR-089). Números chegam como string (`Decimal`) e
// ficam como string: o frontend só apresenta, nunca calcula (ADR-012).

export type ExpansionStatus = 'AMPLIAR' | 'NAO_VALE' | 'EQUILIBRADO' | 'CORRIGIR_ANTES' | 'INDISPONIVEL'
export type InverterStatus = 'OK' | 'VERIFICAR_DATASHEET' | 'NOVO_INVERSOR' | 'MICROINVERSORES' | 'DESCONHECIDO'

export interface ExpansionYearValue {
  year: number
  wireBShare: string
  valueBrlKwh: string
  scenario: boolean
}

export interface ExpansionMoney {
  unavailableReason: string | null
  requestYear: number
  monthlySavingFirstYearBrl: string | null
  monthlySavingScenarioBrl: string | null
  valuesByYear: ExpansionYearValue[]
}

export interface ExpansionPayback {
  unavailableReason: string | null
  proposalBrl: string | null
  includesInverter: boolean | null
  recordedOn: string | null
  paybackMonthsWithIpca: number | null
  paybackMonthsNoGrowth: number | null
  paybackMonthsVsCdi: number | null
  firstYearMonthlySavingBrl: string | null
  tariffGrowthPerYear: string | null
  indicesAsOfMonth: string | null
}

export interface ExpansionAssessment {
  status: ExpansionStatus
  reasons: string[]
  warnings: string[]
  firstMonth: string | null
  lastMonth: string | null
  cyclesUsed: number
  importedKwhTotal: string | null
  exportedKwhTotal: string | null
  deficitKwhYear: string | null
  deficitKwhMonth: string | null
  // Rótulo pronto do backend (falta, sobra ou zero) — a tela não decide pelo sinal.
  direction: 'FALTA' | 'SOBRA' | 'ZERO' | null
  toleranceKwhYear: string | null
  balanceBeforeKwh: string | null
  balanceAfterKwh: string | null
  installedKwp: string | null
  measuredCycles: number
  yieldKwhPerKwpYear: string | null
  extraKwp: string | null
  inverterStatus: InverterStatus
  dcAcRatioAfter: string | null
  problemMonths: string[]
  money: ExpansionMoney | null
  payback: ExpansionPayback | null
}

const STATUSES: readonly ExpansionStatus[] = ['AMPLIAR', 'NAO_VALE', 'EQUILIBRADO', 'CORRIGIR_ANTES', 'INDISPONIVEL']
const DIRECTIONS = ['FALTA', 'SOBRA', 'ZERO'] as const
const INVERTER: readonly InverterStatus[] = [
  'OK',
  'VERIFICAR_DATASHEET',
  'NOVO_INVERSOR',
  'MICROINVERSORES',
  'DESCONHECIDO',
]

type Rec = Record<string, unknown>

function isRecord(value: unknown): value is Rec {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function fail(key: string): never {
  throw new Error(`Resposta inválida da API: ${key}`)
}
function strOrNull(source: Rec, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string' && value.trim() !== '') return value
  fail(key)
}
function int(source: Rec, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isInteger(value)) return value
  fail(key)
}
function strList(source: Rec, key: string): string[] {
  const value = source[key]
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) fail(key)
  return value as string[]
}
function oneOf<T extends string>(source: Rec, key: string, allowed: readonly T[]): T {
  const value = source[key]
  if (typeof value === 'string' && (allowed as readonly string[]).includes(value)) return value as T
  fail(key)
}

function parseMoney(value: unknown): ExpansionMoney | null {
  if (value === null || value === undefined) return null
  if (!isRecord(value)) fail('money')
  const years = value.values_by_year
  if (!Array.isArray(years)) fail('money.values_by_year')
  return {
    unavailableReason: strOrNull(value, 'unavailable_reason'),
    requestYear: int(value, 'request_year'),
    monthlySavingFirstYearBrl: strOrNull(value, 'monthly_saving_first_year_brl'),
    monthlySavingScenarioBrl: strOrNull(value, 'monthly_saving_scenario_brl'),
    valuesByYear: years.map((item) => {
      if (!isRecord(item) || typeof item.scenario !== 'boolean') fail('money.values_by_year')
      const share = strOrNull(item, 'wire_b_share')
      const unit = strOrNull(item, 'value_brl_kwh')
      if (share === null || unit === null) fail('money.values_by_year')
      return { year: int(item, 'year'), wireBShare: share, valueBrlKwh: unit, scenario: item.scenario }
    }),
  }
}

function intOrNull(source: Rec, key: string): number | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  return int(source, key)
}

function parsePayback(value: unknown): ExpansionPayback | null {
  if (value === null || value === undefined) return null
  if (!isRecord(value)) fail('payback')
  const inverter = value.includes_inverter
  if (inverter !== null && inverter !== undefined && typeof inverter !== 'boolean') fail('payback.includes_inverter')
  const premises = value.premises
  if (premises !== null && premises !== undefined && !isRecord(premises)) fail('payback.premises')
  return {
    unavailableReason: strOrNull(value, 'unavailable_reason'),
    proposalBrl: strOrNull(value, 'proposal_brl'),
    includesInverter: typeof inverter === 'boolean' ? inverter : null,
    recordedOn: strOrNull(value, 'recorded_on'),
    paybackMonthsWithIpca: intOrNull(value, 'payback_months_with_ipca'),
    paybackMonthsNoGrowth: intOrNull(value, 'payback_months_no_growth'),
    paybackMonthsVsCdi: intOrNull(value, 'payback_months_vs_cdi'),
    firstYearMonthlySavingBrl: strOrNull(value, 'first_year_monthly_saving_brl'),
    tariffGrowthPerYear: isRecord(premises) ? strOrNull(premises, 'tariff_growth_per_year') : null,
    indicesAsOfMonth: strOrNull(value, 'indices_as_of_month'),
  }
}

export function parseExpansionAssessment(payload: unknown): ExpansionAssessment {
  if (!isRecord(payload)) fail('payload')
  return {
    status: oneOf(payload, 'status', STATUSES),
    reasons: strList(payload, 'reasons'),
    warnings: strList(payload, 'warnings'),
    firstMonth: strOrNull(payload, 'first_month'),
    lastMonth: strOrNull(payload, 'last_month'),
    cyclesUsed: int(payload, 'cycles_used'),
    importedKwhTotal: strOrNull(payload, 'imported_kwh_total'),
    exportedKwhTotal: strOrNull(payload, 'exported_kwh_total'),
    deficitKwhYear: strOrNull(payload, 'deficit_kwh_year'),
    deficitKwhMonth: strOrNull(payload, 'deficit_kwh_month'),
    direction: payload.direction == null ? null : oneOf(payload, 'direction', DIRECTIONS),
    toleranceKwhYear: strOrNull(payload, 'tolerance_kwh_year'),
    balanceBeforeKwh: strOrNull(payload, 'balance_before_kwh'),
    balanceAfterKwh: strOrNull(payload, 'balance_after_kwh'),
    installedKwp: strOrNull(payload, 'installed_kwp'),
    measuredCycles: int(payload, 'measured_cycles'),
    yieldKwhPerKwpYear: strOrNull(payload, 'yield_kwh_per_kwp_year'),
    extraKwp: strOrNull(payload, 'extra_kwp'),
    inverterStatus: oneOf(payload, 'inverter_status', INVERTER),
    dcAcRatioAfter: strOrNull(payload, 'dc_ac_ratio_after'),
    problemMonths: strList(payload, 'problem_months'),
    money: parseMoney(payload.money),
    payback: parsePayback(payload.payback),
  }
}
