// Parser do contrato de `GET /reports/monthly/history` (histórico de produção
// por ciclo de faturamento, usado pelo gráfico `MonthlyProductionSection`).
// Arquivo separado dos demais parsers de `dashboard/` pelo mesmo motivo de
// `financial-return-contracts.ts`/`photovoltaic-contracts.ts`: vocabulário e
// forma de indisponibilidade próprios (ciclos fechados, sem estado "em
// curso"), que não se misturam com o contrato de `/energy/executive/latest`.
//
// `production_kwh` chega como string (`Decimal` serializado) ou `null` —
// nunca `0` como substituto de ausência (ver skill `chart-standards`) —
// convertido para número só neste parser, porque aqui o valor alimenta
// diretamente `BarList`, que espera `number | null`.

export interface MonthlyProductionCycleQuality {
  missingDays: number | null
  provisionalDays: number | null
  incompleteDays: number | null
  unavailableDays: number | null
}

export interface MonthlyProductionCycle {
  referenceMonth: string
  billId: string
  status: string
  productionKwh: number | null
  quality: MonthlyProductionCycleQuality | null
}

export interface MonthlyProductionHistoryResponse {
  plantId: string
  limit: number
  cyclesReturned: number
  cycles: MonthlyProductionCycle[]
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

function numberValue(source: Record<string, unknown>, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

// Nunca lança para `null`/`undefined` — `production_kwh` legitimamente vem
// `null` quando o ciclo fechado não tem produção diária suficiente para
// consolidar um total (ver contrato do endpoint). Diferente do resto do
// dashboard, aqui o parser já converte para `number`, porque o consumidor
// (`BarList`) trabalha com `number | null`, não com a string decimal crua.
function nullableDecimalNumber(source: Record<string, unknown>, key: string): number | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string') {
    const numeric = Number(value)
    if (Number.isFinite(numeric)) return numeric
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  throw new Error(`Resposta inválida da API: ${key}`)
}

function nullableInt(source: Record<string, unknown>, key: string): number | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'number' && Number.isFinite(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

// O objeto `quality` inteiro pode vir `null` quando o snapshot não tem
// nenhuma das quatro chaves (ver contrato do endpoint) — distinto de um
// objeto presente com os quatro contadores `null` individualmente, mas
// ambos os casos resultam no mesmo estado para quem consome (nenhuma lacuna
// conhecida a reportar).
function parseQuality(value: unknown): MonthlyProductionCycleQuality | null {
  if (value === null || value === undefined) return null
  if (!isRecord(value)) throw new Error('Resposta inválida da API: quality')
  return {
    missingDays: nullableInt(value, 'missing_days'),
    provisionalDays: nullableInt(value, 'provisional_days'),
    incompleteDays: nullableInt(value, 'incomplete_days'),
    unavailableDays: nullableInt(value, 'unavailable_days'),
  }
}

function parseCycle(value: unknown): MonthlyProductionCycle {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: cycles[]')
  return {
    referenceMonth: requireString(value, 'reference_month'),
    billId: requireString(value, 'bill_id'),
    status: requireString(value, 'status'),
    productionKwh: nullableDecimalNumber(value, 'production_kwh'),
    quality: parseQuality(value.quality),
  }
}

export function parseMonthlyProductionHistory(payload: unknown): MonthlyProductionHistoryResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const cycles = payload.cycles
  if (!Array.isArray(cycles)) throw new Error('Resposta inválida da API: cycles')
  return {
    plantId: requireString(payload, 'plant_id'),
    limit: numberValue(payload, 'limit'),
    cyclesReturned: numberValue(payload, 'cycles_returned'),
    cycles: cycles.map(parseCycle),
  }
}
