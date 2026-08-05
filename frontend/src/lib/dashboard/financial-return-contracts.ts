// Parser do contrato de `GET /energy/financial-return/latest` (ADR-067, Decisão
// item 5, "Etapa E — frontend"). Arquivo separado de `contracts.ts` pelo mesmo
// motivo de `photovoltaic-contracts.ts`: vocabulário e forma de indisponibilidade
// próprios, que não se misturam com o contrato de `/energy/executive/latest`.
//
// Todos os valores monetários chegam como string (`Decimal` serializado, ver
// `intelligence/router.py::_serialize_financial_return`) e são convertidos só na
// hora de calcular/formatar, igual ao resto do dashboard.

// Enum único compartilhado entre `unavailable_reason` e
// `payback_unavailable_reason` (ver
// `intelligence/financial_return_service.py::FinancialReturnUnavailableReason`).
// A separação em dois campos no contrato existe justamente para que um ROI válido
// não fique escondido atrás de um payback sem histórico suficiente — ver ADR-067,
// Decisão item 5.
export type FinancialReturnUnavailableReason =
  | 'INVESTMENT_NOT_REGISTERED'
  | 'NO_CONSOLIDATED_SAVINGS'
  | 'INSUFFICIENT_HISTORY'

const FINANCIAL_RETURN_UNAVAILABLE_REASONS: ReadonlySet<string> = new Set([
  'INVESTMENT_NOT_REGISTERED',
  'NO_CONSOLIDATED_SAVINGS',
  'INSUFFICIENT_HISTORY',
])

export interface FinancialReturnResponse {
  plant_id: string
  investment_amount_brl: string | null
  investment_recorded_on: string | null
  commissioned_on: string | null
  accumulated_savings_brl: string | null
  average_monthly_savings_brl: string | null
  cycles_counted: number | null
  cycles_expected: number | null
  roi_percent: string | null
  payback_projection_months: number | null
  unavailable_reason: FinancialReturnUnavailableReason | null
  payback_unavailable_reason: FinancialReturnUnavailableReason | null
}

// Espelha `PlantFinancialConfigurationView` (`plants/router.py`) — usado tanto
// pelo `GET` quanto pela resposta do `PATCH /plants/{plant_id}/financial-configuration`.
export interface PlantFinancialConfiguration {
  plant_id: string
  investment_amount_brl: string | null
  investment_recorded_on: string | null
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

// Nunca lança para `null`/`undefined` — todos os campos derivados do retorno
// financeiro vêm `null` em algum estado de indisponibilidade legítimo (ver
// ADR-067, Decisão item 5), e o parser precisa aceitar isso sem exceção.
function nullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function nullableNumber(source: Record<string, unknown>, key: string): number | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'number' && Number.isFinite(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

// Motivo desconhecido vira `null` em vez de lançar — mesmo princípio defensivo de
// `parseBaselineUnavailableReason` em `photovoltaic-contracts.ts`: um backend mais
// novo pode acrescentar um motivo que este frontend ainda não conhece, e a seção
// deve degradar para "sem motivo específico" em vez de quebrar a página inteira.
function parseFinancialReturnUnavailableReason(
  value: unknown
): FinancialReturnUnavailableReason | null {
  if (typeof value === 'string' && FINANCIAL_RETURN_UNAVAILABLE_REASONS.has(value)) {
    return value as FinancialReturnUnavailableReason
  }
  return null
}

export function parseFinancialReturn(payload: unknown): FinancialReturnResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  return {
    plant_id: requireString(payload, 'plant_id'),
    investment_amount_brl: nullableString(payload, 'investment_amount_brl'),
    investment_recorded_on: nullableString(payload, 'investment_recorded_on'),
    commissioned_on: nullableString(payload, 'commissioned_on'),
    accumulated_savings_brl: nullableString(payload, 'accumulated_savings_brl'),
    average_monthly_savings_brl: nullableString(payload, 'average_monthly_savings_brl'),
    cycles_counted: nullableNumber(payload, 'cycles_counted'),
    cycles_expected: nullableNumber(payload, 'cycles_expected'),
    roi_percent: nullableString(payload, 'roi_percent'),
    payback_projection_months: nullableNumber(payload, 'payback_projection_months'),
    unavailable_reason: parseFinancialReturnUnavailableReason(payload.unavailable_reason),
    payback_unavailable_reason: parseFinancialReturnUnavailableReason(
      payload.payback_unavailable_reason
    ),
  }
}

export function parseFinancialConfiguration(payload: unknown): PlantFinancialConfiguration {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  return {
    plant_id: requireString(payload, 'plant_id'),
    investment_amount_brl: nullableString(payload, 'investment_amount_brl'),
    investment_recorded_on: nullableString(payload, 'investment_recorded_on'),
  }
}

// Mesmo princípio de `savingsUnavailableMessage`/`baselineUnavailableMessage`:
// mensagem específica por motivo, nunca um card vazio silencioso. `INSUFFICIENT_HISTORY`
// nunca é o motivo de indisponibilidade do ROI em si (só do payback — ver
// `paybackUnavailableMessage`), mas o `switch` cobre o caso por completude do tipo.
export function financialReturnUnavailableMessage(reason: FinancialReturnUnavailableReason): string {
  switch (reason) {
    case 'INVESTMENT_NOT_REGISTERED':
      return 'Retorno do investimento ainda não disponível — cadastre o valor investido nesta usina para calcular o ROI.'
    case 'NO_CONSOLIDATED_SAVINGS':
      return 'Retorno do investimento ainda não disponível — nenhum ciclo com relatório consolidado tem economia calculada até agora.'
    case 'INSUFFICIENT_HISTORY':
      return 'Retorno do investimento ainda não disponível.'
  }
}

// Mensagem específica para o payback quando o ROI já está disponível mas a
// projeção não (ver ADR-067, Decisão item 5: piso de 6 ciclos consolidados e
// economia média mensal positiva).
export function paybackUnavailableMessage(reason: FinancialReturnUnavailableReason): string {
  switch (reason) {
    case 'INSUFFICIENT_HISTORY':
      return 'Projeção de payback ainda não disponível — são necessários ao menos 6 ciclos com relatório consolidado e economia média mensal positiva.'
    case 'INVESTMENT_NOT_REGISTERED':
    case 'NO_CONSOLIDATED_SAVINGS':
      return 'Projeção de payback ainda não disponível.'
  }
}

// O backend sinaliza payback já atingido devolvendo `payback_projection_months
// == cycles_counted` (ver `financial_return_service.py::get_latest_financial_return`,
// ramo `accumulated_savings_brl >= investment_amount_brl`) — não há um campo booleano
// dedicado, então o frontend deriva a partir dessa igualdade, documentada aqui para
// não virar "mágica" sem explicação no componente que a consome.
export function isPaybackAlreadyReached(result: FinancialReturnResponse): boolean {
  return (
    result.payback_projection_months !== null &&
    result.cycles_counted !== null &&
    result.payback_projection_months === result.cycles_counted
  )
}

// Cobertura parcial: há menos ciclos consolidados do que meses decorridos desde o
// comissionamento. Quando `cycles_expected` é `null` (usina sem `commissioned_on`),
// a interface não tem base para comparar e não deve fingir cobertura completa nem
// incompleta — por isso este helper só retorna `true` com os dois valores presentes.
export function hasPartialCoverage(result: FinancialReturnResponse): boolean {
  return (
    result.cycles_counted !== null &&
    result.cycles_expected !== null &&
    result.cycles_counted < result.cycles_expected
  )
}

export function coverageLabel(result: FinancialReturnResponse): string | null {
  if (!hasPartialCoverage(result)) return null
  return `Baseado em ${result.cycles_counted} de ${result.cycles_expected} ciclos com relatório consolidado.`
}
