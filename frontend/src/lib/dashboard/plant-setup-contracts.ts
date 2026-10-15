// Parser de `GET /plants/{plant_id}/setup` (ver `plants/schemas.py::
// PlantSetupView`). Números chegam como string (`Decimal`) ou `null` e ficam
// assim — nenhum valor ausente vira zero.

export type PlantSetupItemKey =
  | 'LOCATION'
  | 'DC_CAPACITY'
  | 'COMMISSIONED_ON'
  | 'ORIENTATION'
  | 'MODULE_TECHNOLOGY'
  | 'INVESTMENT'
  | 'CONFIRMED_BILL'

export type ModuleTechnology =
  | 'MONOCRYSTALLINE_SILICON'
  | 'POLYCRYSTALLINE_SILICON'
  | 'THIN_FILM'
  | 'OTHER'

export interface PlantSetupItem {
  key: PlantSetupItemKey
  done: boolean
}

export interface PlantSetup {
  plantId: string
  name: string
  dcCapacityKwp: string | null
  acCapacityKw: string | null
  arrayTiltDegrees: string | null
  arrayAzimuthDegrees: string | null
  moduleTechnology: ModuleTechnology | null
  commissionedOn: string | null
  deviceCount: number
  latitude: string | null
  longitude: string | null
  investmentAmountBrl: string | null
  investmentRecordedOn: string | null
  confirmedBills: number
  pendingBills: number
  items: PlantSetupItem[]
  completed: number
  total: number
}

const ITEM_KEYS: readonly PlantSetupItemKey[] = [
  'LOCATION',
  'DC_CAPACITY',
  'COMMISSIONED_ON',
  'ORIENTATION',
  'MODULE_TECHNOLOGY',
  'INVESTMENT',
  'CONFIRMED_BILL',
]
const TECHNOLOGIES: readonly ModuleTechnology[] = [
  'MONOCRYSTALLINE_SILICON',
  'POLYCRYSTALLINE_SILICON',
  'THIN_FILM',
  'OTHER',
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function fail(key: string): never {
  throw new Error(`Resposta inválida da API: ${key}`)
}

function requireRecord(source: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = source[key]
  if (!isRecord(value)) fail(key)
  return value
}

function requireString(source: Record<string, unknown>, key: string): string {
  const value = source[key]
  if (typeof value !== 'string' || value.trim() === '') fail(key)
  return value
}

// Decimal do Pydantic pode chegar como string ou número, conforme a
// serialização; normalizado para string.
function nullableDecimal(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  fail(key)
}

function nullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  fail(key)
}

function requireCount(source: Record<string, unknown>, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isInteger(value) && value >= 0) return value
  fail(key)
}

export function parsePlantSetup(payload: unknown): PlantSetup {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const technical = requireRecord(payload, 'technical')
  const financial = requireRecord(payload, 'financial')
  const rawItems = payload.items
  if (!Array.isArray(rawItems)) fail('items')
  const items = rawItems.map((raw): PlantSetupItem => {
    if (!isRecord(raw)) fail('items[]')
    const key = requireString(raw, 'key')
    if (!(ITEM_KEYS as readonly string[]).includes(key)) fail('items[].key')
    if (typeof raw.done !== 'boolean') fail('items[].done')
    return { key: key as PlantSetupItemKey, done: raw.done }
  })
  const technology = nullableString(technical, 'module_technology')
  if (technology !== null && !(TECHNOLOGIES as readonly string[]).includes(technology)) {
    fail('module_technology')
  }
  const devices = technical.devices
  if (!Array.isArray(devices)) fail('devices')
  return {
    plantId: requireString(payload, 'plant_id'),
    name: requireString(payload, 'name'),
    dcCapacityKwp: nullableDecimal(technical, 'dc_capacity_kwp'),
    acCapacityKw: nullableDecimal(technical, 'ac_capacity_kw'),
    arrayTiltDegrees: nullableDecimal(technical, 'array_tilt_degrees'),
    arrayAzimuthDegrees: nullableDecimal(technical, 'array_azimuth_degrees'),
    moduleTechnology: technology as ModuleTechnology | null,
    commissionedOn: nullableString(technical, 'commissioned_on'),
    deviceCount: devices.length,
    latitude: nullableDecimal(payload, 'latitude'),
    longitude: nullableDecimal(payload, 'longitude'),
    investmentAmountBrl: nullableDecimal(financial, 'investment_amount_brl'),
    investmentRecordedOn: nullableString(financial, 'investment_recorded_on'),
    confirmedBills: requireCount(payload, 'confirmed_bills'),
    pendingBills: requireCount(payload, 'pending_bills'),
    items,
    completed: requireCount(payload, 'completed'),
    total: requireCount(payload, 'total'),
  }
}
