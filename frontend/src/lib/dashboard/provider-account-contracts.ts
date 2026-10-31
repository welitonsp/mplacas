// Parser de `GET/PUT /plants/{plant_id}/provider-account` (ADR-091,
// `providers/router.py::ProviderAccountView`). A resposta nunca traz login
// completo nem senha; o estado (`SEM_CONEXAO`, `CONECTADA`, `FALHA`) vem
// decidido do backend e não é recalculado aqui.

export type ProviderConnectionStatus = 'SEM_CONEXAO' | 'CONECTADA' | 'FALHA'

export interface ProviderAccount {
  status: ProviderConnectionStatus
  provider: string | null
  loginHint: string | null
  connectedAt: string | null
  lastSuccessAt: string | null
  lastFailureAt: string | null
  devicesFound: number | null
}

const STATUSES: readonly ProviderConnectionStatus[] = ['SEM_CONEXAO', 'CONECTADA', 'FALHA']

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function fail(key: string): never {
  throw new Error(`Resposta inválida da API: ${key}`)
}

function nullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  if (value == null) return null
  if (typeof value !== 'string' || value.trim() === '') fail(key)
  return value
}

export function parseProviderAccount(payload: unknown): ProviderAccount {
  if (!isRecord(payload)) fail('provider_account')
  const status = payload.status
  if (typeof status !== 'string' || !STATUSES.includes(status as ProviderConnectionStatus)) {
    fail('status')
  }
  const devices = payload.devices_found
  if (devices != null && (typeof devices !== 'number' || !Number.isInteger(devices) || devices < 0)) {
    fail('devices_found')
  }
  return {
    status: status as ProviderConnectionStatus,
    provider: nullableString(payload, 'provider'),
    loginHint: nullableString(payload, 'login_hint'),
    connectedAt: nullableString(payload, 'connected_at'),
    lastSuccessAt: nullableString(payload, 'last_success_at'),
    lastFailureAt: nullableString(payload, 'last_failure_at'),
    devicesFound: devices == null ? null : (devices as number),
  }
}

// Marcas que o cliente pode escolher (ADR-091/092). O rótulo é o nome do app
// que o dono conhece; o valor é o que o backend espera.
export type ProviderBrand = 'NEPVIEWER' | 'GROWATT'

export const PROVIDER_BRANDS: ReadonlyArray<{ value: ProviderBrand; label: string; app: string }> = [
  { value: 'NEPVIEWER', label: 'NEPViewer', app: 'NEPViewer' },
  { value: 'GROWATT', label: 'Growatt', app: 'ShinePhone (Growatt)' },
]

export function brandLabel(provider: string | null | undefined): string {
  return PROVIDER_BRANDS.find((brand) => brand.value === provider)?.label ?? 'fabricante'
}

// Mensagens por código de erro do backend (`detail`). Nenhuma repete o que o
// usuário digitou. `{marca}` vira o nome da marca escolhida.
const ERROR_MESSAGES: Record<string, string> = {
  provider_login_failed: 'A {marca} recusou o usuário ou a senha. Confira e tente de novo.',
  provider_login_invalid: 'Informe o usuário do app {marca}.',
  provider_password_invalid: 'Informe a senha do app {marca}.',
  provider_unavailable: 'A {marca} não respondeu agora. Tente de novo em alguns minutos.',
  provider_rate_limited:
    'A {marca} bloqueou novas tentativas por um tempo. Espere cerca de uma hora e tente de novo.',
  provider_unsupported: 'Esta marca ainda não é aceita.',
  provider_inverter_in_another_plant:
    'Algum inversor desta conta já está ligado a outra usina. Fale com o suporte.',
  provider_account_in_use: 'Esta conta da {marca} já está conectada a outra usina.',
  provider_verify_rate_limited: 'Muitas tentativas seguidas. Espere alguns minutos e tente de novo.',
  provider_account_not_found: 'Esta usina já estava sem conta conectada.',
  provider_secret_keys_not_configured:
    'O servidor ainda não está pronto para guardar a senha. Fale com o suporte.',
}

export async function providerAccountErrorMessage(
  response: Response,
  provider: string | null = null,
): Promise<string> {
  if (response.status === 403) return 'Só o administrador da conta pode alterar a conexão.'
  let code: unknown
  try {
    code = ((await response.json()) as { detail?: unknown })?.detail
  } catch {
    code = undefined
  }
  if (typeof code === 'string' && code in ERROR_MESSAGES) {
    return ERROR_MESSAGES[code].split('{marca}').join(brandLabel(provider))
  }
  if (response.status === 404) return 'Usina não encontrada.'
  return 'Não foi possível concluir agora. Tente novamente.'
}
