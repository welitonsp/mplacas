// Parsers do fluxo de entrada de clientes (ADR-093): convite, quem sou eu,
// clientes do dono e primeira conexão. Nenhum deles guarda token ou senha.

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function fail(key: string): never {
  throw new Error(`Resposta inválida da API: ${key}`)
}

function requireString(source: Record<string, unknown>, key: string): string {
  const value = source[key]
  if (typeof value !== 'string' || value.trim() === '') fail(key)
  return value
}

function nullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value == null) return null
  if (typeof value !== 'string') fail(key)
  return value
}

function requireCount(source: Record<string, unknown>, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isInteger(value) && value >= 0) return value
  fail(key)
}

// --- GET /auth/me -----------------------------------------------------------

export interface Me {
  username: string | null
  role: 'ADMIN' | 'READ'
  organizationName: string | null
  isPlatformOperator: boolean
}

export function parseMe(payload: unknown): Me {
  if (!isRecord(payload)) fail('me')
  const role = payload.role
  if (role !== 'ADMIN' && role !== 'READ') fail('role')
  if (typeof payload.is_platform_operator !== 'boolean') fail('is_platform_operator')
  return {
    username: nullableString(payload, 'username'),
    role,
    organizationName: nullableString(payload, 'organization_name'),
    isPlatformOperator: payload.is_platform_operator,
  }
}

// --- POST /auth/invitations/inspect ------------------------------------------

export interface InvitationPreview {
  organizationName: string
  username: string
  expiresAt: string
}

export function parseInvitationPreview(payload: unknown): InvitationPreview {
  if (!isRecord(payload)) fail('invitation')
  return {
    organizationName: requireString(payload, 'organization_name'),
    username: requireString(payload, 'username'),
    expiresAt: requireString(payload, 'expires_at'),
  }
}

// Senha mínima do convite (`auth/router.py::_MIN_INVITATION_PASSWORD_LENGTH`).
// Conferida aqui antes de enviar: o 422 do servidor repetiria o que foi digitado.
export const INVITATION_MIN_PASSWORD = 12
export const INVITATION_MAX_PASSWORD = 200

// O token vem no fragmento (`#token=...`), que o navegador nunca envia ao
// servidor nem ao `Referer`. Aceita também `#...` puro.
export function readInvitationToken(hash: string): string | null {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash
  if (!raw) return null
  const params = new URLSearchParams(raw)
  const token = params.get('token') ?? (raw.includes('=') ? null : raw)
  return token && token.trim() ? token.trim() : null
}

export function buildInvitationLink(origin: string, token: string): string {
  return `${origin.replace(/\/$/, '')}/convite#token=${encodeURIComponent(token)}`
}

// --- /platform/clients -------------------------------------------------------

export interface ClientSummary {
  organizationId: string
  name: string
  active: boolean
  createdAt: string | null
  users: number
  plants: number
  connections: number
  adminUsername: string | null
  invitationPendingUntil: string | null
}

export function parseClients(payload: unknown): ClientSummary[] {
  if (!isRecord(payload) || !Array.isArray(payload.items)) fail('items')
  return payload.items.map((raw): ClientSummary => {
    if (!isRecord(raw)) fail('items[]')
    if (typeof raw.active !== 'boolean') fail('active')
    return {
      organizationId: requireString(raw, 'organization_id'),
      name: requireString(raw, 'name'),
      active: raw.active,
      createdAt: nullableString(raw, 'created_at'),
      users: requireCount(raw, 'users'),
      plants: requireCount(raw, 'plants'),
      connections: requireCount(raw, 'connections'),
      adminUsername: nullableString(raw, 'admin_username'),
      invitationPendingUntil: nullableString(raw, 'invitation_pending_until'),
    }
  })
}

export interface ClientInvitation {
  organizationId: string
  username: string
  expiresAt: string
  token: string
}

export function parseClientInvitation(payload: unknown): ClientInvitation {
  if (!isRecord(payload)) fail('client')
  const invitation = payload.invitation
  if (!isRecord(invitation)) fail('invitation')
  return {
    organizationId: requireString(payload, 'organization_id'),
    username: requireString(invitation, 'username'),
    expiresAt: requireString(invitation, 'expires_at'),
    token: requireString(invitation, 'token'),
  }
}

const CLIENT_ERRORS: Record<string, string> = {
  client_admin_username_invalid: 'Informe um e-mail válido para o cliente.',
  client_slug_in_use: 'Já existe um cliente com esse nome. Tente de novo em instantes.',
  client_not_found: 'Cliente não encontrado.',
}

export async function clientErrorMessage(response: Response): Promise<string> {
  if (response.status === 403) return 'Só o dono da plataforma pode cadastrar clientes.'
  let code: unknown
  try {
    code = ((await response.json()) as { detail?: unknown })?.detail
  } catch {
    code = undefined
  }
  if (typeof code === 'string' && code in CLIENT_ERRORS) return CLIENT_ERRORS[code]
  if (response.status === 422) return 'Confira o nome e o e-mail do cliente.'
  return 'Não foi possível concluir agora. Tente novamente.'
}

// --- POST /plants/connect ----------------------------------------------------

export type AutoFillOrigin = 'BRAND' | 'ESTIMATE'

export interface FirstConnection {
  plantId: string
  plantName: string
  devicesFound: number | null
  autoFilled: Record<string, AutoFillOrigin>
}

export function parseFirstConnection(payload: unknown): FirstConnection {
  if (!isRecord(payload)) fail('first_connection')
  const connection = payload.connection
  if (!isRecord(connection)) fail('connection')
  const devices = connection.devices_found
  if (devices != null && (typeof devices !== 'number' || !Number.isInteger(devices) || devices < 0)) {
    fail('devices_found')
  }
  const rawFilled = payload.auto_filled
  if (!isRecord(rawFilled)) fail('auto_filled')
  const autoFilled: Record<string, AutoFillOrigin> = {}
  for (const [field, origin] of Object.entries(rawFilled)) {
    if (origin !== 'BRAND' && origin !== 'ESTIMATE') fail('auto_filled')
    autoFilled[field] = origin
  }
  return {
    plantId: requireString(payload, 'plant_id'),
    plantName: requireString(payload, 'plant_name'),
    devicesFound: devices == null ? null : (devices as number),
    autoFilled,
  }
}

// Rótulo de cada campo preenchido sozinho, na língua do dono da usina.
export const AUTO_FILL_LABELS: Record<string, string> = {
  name: 'Nome da usina',
  dc_capacity_kwp: 'Potência dos painéis',
  location: 'Localização',
  array_tilt_degrees: 'Inclinação dos painéis',
  array_azimuth_degrees: 'Direção dos painéis',
  module_technology: 'Tipo de painel',
}
