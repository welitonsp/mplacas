import { DASHBOARD_ROOT_PATH } from '../routes'

export interface LoginOrigin {
  pathname: string
  search: string
  hash: string
}

// Destino pós-login vindo de `location.state.from`. O `state` do router só vive
// em memória/histórico da própria aba, mas o valor é tratado como não confiável
// mesmo assim: só caminhos internos sob /dashboard são aceitos (sem open
// redirect); qualquer outra coisa cai no painel.
function isSafeDashboardPath(pathname: unknown): pathname is string {
  if (typeof pathname !== 'string') return false
  if (pathname.startsWith('//')) return false
  if (pathname.includes('\\') || pathname.includes(':')) return false
  return (
    pathname === DASHBOARD_ROOT_PATH || pathname.startsWith(`${DASHBOARD_ROOT_PATH}/`)
  )
}

export function resolvePostLoginPath(state: unknown): string {
  const from = (state as { from?: Partial<LoginOrigin> } | null)?.from
  if (!from || !isSafeDashboardPath(from.pathname)) return DASHBOARD_ROOT_PATH
  const search = typeof from.search === 'string' && from.search.startsWith('?') && !from.search.includes('\\') ? from.search : ''
  const hash = typeof from.hash === 'string' && from.hash.startsWith('#') && !from.hash.includes('\\') ? from.hash : ''
  return `${from.pathname}${search}${hash}`
}
