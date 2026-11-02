// Contratos da área Clientes do dono (ADR-095): etapas do funil, ficha e
// histórico. Separados do onboarding (convite, primeira conexão) para só a
// página Clientes carregar este código.
import { fail, isRecord, nullableString, requireCount, requireString } from './onboarding-contracts'

// Etapas do cliente (ADR-095), decididas no backend (`clients/router.py::_stage`).
export type ClientStage =
  | 'CONVIDADO'
  | 'CONVITE_VENCIDO'
  | 'ENTROU'
  | 'USINA_CONECTADA'
  | 'RECEBENDO_DADOS'
  | 'COM_FALHA'
  | 'DESATIVADO'

const STAGES: readonly ClientStage[] = [
  'CONVIDADO',
  'CONVITE_VENCIDO',
  'ENTROU',
  'USINA_CONECTADA',
  'RECEBENDO_DADOS',
  'COM_FALHA',
  'DESATIVADO',
]

export function parseStage(source: Record<string, unknown>): ClientStage {
  const value = source.stage
  if (typeof value !== 'string' || !(STAGES as readonly string[]).includes(value)) fail('stage')
  return value as ClientStage
}

export const STAGE_COPY: Record<ClientStage, { label: string; tone: 'neutral' | 'progress' | 'ok' | 'warn' | 'off' }> = {
  CONVIDADO: { label: 'Convidado', tone: 'neutral' },
  CONVITE_VENCIDO: { label: 'Convite vencido', tone: 'warn' },
  ENTROU: { label: 'Entrou, falta conectar a usina', tone: 'progress' },
  USINA_CONECTADA: { label: 'Usina conectada, aguardando a 1ª leitura', tone: 'progress' },
  RECEBENDO_DADOS: { label: 'Recebendo dados', tone: 'ok' },
  COM_FALHA: { label: 'Com falha na leitura', tone: 'warn' },
  DESATIVADO: { label: 'Desativado', tone: 'off' },
}

// --- GET /platform/clients/{id} (ficha, ADR-095) -----------------------------

export interface ClientActivity {
  action: string
  outcome: string
  at: string
  details: Record<string, unknown>
}

export interface ClientDetail {
  organizationId: string
  name: string
  active: boolean
  createdAt: string | null
  stage: ClientStage
  adminUsername: string | null
  hasUser: boolean
  plants: Array<{ plantId: string; name: string; installedPowerKwp: string | null }>
  connection: {
    provider: string
    connectedAt: string | null
    lastSuccessAt: string | null
    lastFailureAt: string | null
    lastFailureCode: string | null
  } | null
  pendingLink: { purpose: 'INVITE' | 'RESET'; expiresAt: string } | null
  activity: ClientActivity[]
}

export function parseClientDetail(payload: unknown): ClientDetail {
  if (!isRecord(payload)) fail('client')
  if (typeof payload.active !== 'boolean') fail('active')
  const users = payload.users
  const plants = payload.plants
  const activity = payload.activity
  if (!Array.isArray(users) || !Array.isArray(plants) || !Array.isArray(activity)) fail('client')
  const connection = payload.connection
  const pending = payload.pending_link
  return {
    organizationId: requireString(payload, 'organization_id'),
    name: requireString(payload, 'name'),
    active: payload.active,
    createdAt: nullableString(payload, 'created_at'),
    stage: parseStage(payload),
    adminUsername: nullableString(payload, 'admin_username'),
    hasUser: users.some((user) => isRecord(user) && user.active === true),
    plants: plants.map((raw) => {
      if (!isRecord(raw)) fail('plants[]')
      const power = raw.installed_power_kwp
      return {
        plantId: requireString(raw, 'plant_id'),
        name: requireString(raw, 'name'),
        installedPowerKwp: power == null ? null : String(power),
      }
    }),
    connection: isRecord(connection)
      ? {
          provider: requireString(connection, 'provider'),
          connectedAt: nullableString(connection, 'connected_at'),
          lastSuccessAt: nullableString(connection, 'last_success_at'),
          lastFailureAt: nullableString(connection, 'last_failure_at'),
          lastFailureCode: nullableString(connection, 'last_failure_code'),
        }
      : null,
    pendingLink: isRecord(pending)
      ? {
          purpose: pending.purpose === 'RESET' ? 'RESET' : 'INVITE',
          expiresAt: requireString(pending, 'expires_at'),
        }
      : null,
    activity: activity.map((raw) => {
      if (!isRecord(raw)) fail('activity[]')
      return {
        action: requireString(raw, 'action'),
        outcome: requireString(raw, 'outcome'),
        at: requireString(raw, 'at'),
        details: isRecord(raw.details) ? raw.details : {},
      }
    }),
  }
}

// Histórico em português: ação → frase; motivo da recusa → explicação.
const ACTIVITY_LABELS: Record<string, string> = {
  'platform.client_created': 'Cliente cadastrado e convite gerado',
  'platform.client_invited': 'Novo convite gerado',
  'platform.client_access_reset': 'Link para redefinir o acesso gerado',
  'platform.client_deactivated': 'Cliente desativado',
  'platform.client_reactivated': 'Cliente reativado',
  'invitations.accept': 'Cliente aceitou o convite e criou a senha',
  'invitations.access_reset': 'Cliente criou uma senha nova',
  'plant.created_from_connection': 'Usina criada pela conexão com a marca',
  'provider_account.saved': 'Conexão com a marca salva',
  'provider_account.profile_refreshed': 'Dados da usina relidos na marca',
  'provider_account.history_imported': 'Produção dos últimos 90 dias importada',
  'provider_account.history_import_failed': 'Importação da produção falhou',
  'provider_account.verify_failed': 'Tentativa de conexão com a marca recusada',
  'provider_account.removed': 'Conexão com a marca desligada',
}

const REASON_LABELS: Record<string, string> = {
  provider_login_failed: 'a marca recusou o usuário ou a senha',
  provider_token_failed: 'a Growatt recusou o token',
  provider_login_blocked: 'a Growatt bloqueou o login por senha (use o token)',
  provider_unavailable: 'a marca não respondeu',
  provider_rate_limited: 'a marca bloqueou por excesso de tentativas',
  provider_inverter_in_another_plant: 'a usina já está ligada a outra conta',
  provider_account_in_use: 'esta conta já está ligada a outra usina',
}

export function describeActivity(item: ClientActivity): string {
  const base = ACTIVITY_LABELS[item.action] ?? item.action
  const reason = item.details.reason
  if (typeof reason === 'string' && reason in REASON_LABELS) return `${base}: ${REASON_LABELS[reason]}`
  return base
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
  stage: ClientStage
  lastSuccessAt: string | null
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
      stage: parseStage(raw),
      lastSuccessAt: nullableString(raw, 'last_success_at'),
    }
  })
}

const CLIENT_ERRORS: Record<string, string> = {
  client_has_no_user: 'O cliente ainda não entrou: use “Novo convite”.',
  client_inactive: 'Reative o cliente antes de redefinir o acesso.',
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

