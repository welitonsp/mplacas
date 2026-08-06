// Parser do contrato de `GET /plants` (ADR-069, seção 4, "Contrato de resposta:
// mínimo suficiente para o seletor"). Arquivo separado dos demais parsers de
// `dashboard/` porque este endpoint não pertence a um ciclo/usina específica —
// é a lista de usinas da organização inteira, consumida pelo seletor (Etapa D)
// e pelo `PlantContext` (Etapa C), nenhum dos dois implementados ainda aqui.
//
// `installed_power_kwp` chega como string (`Decimal` serializado) ou `null`,
// igual à convenção do resto do dashboard — nunca convertido para número neste
// parser, só na hora de exibir/calcular.

export interface Plant {
  id: string
  name: string
  installedPowerKwp: string | null
}

export interface PlantsResponse {
  count: number
  items: Plant[]
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
  if (value === null) return null
  if (typeof value === 'string') return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function numberValue(source: Record<string, unknown>, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  throw new Error(`Resposta inválida da API: ${key}`)
}

function parsePlant(value: unknown): Plant {
  if (!isRecord(value)) throw new Error('Resposta inválida da API: items[]')
  return {
    id: requireString(value, 'id'),
    name: requireString(value, 'name'),
    installedPowerKwp: nullableString(value, 'installed_power_kwp'),
  }
}

export function parsePlantsResponse(payload: unknown): PlantsResponse {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const items = payload.items
  if (!Array.isArray(items)) throw new Error('Resposta inválida da API: items')
  return {
    count: numberValue(payload, 'count'),
    items: items.map(parsePlant),
  }
}
