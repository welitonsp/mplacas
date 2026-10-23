import { Navigate, useLocation } from 'react-router'
import { DASHBOARD_DEFAULT_PATH } from '../../routes'

// Redirect de `/dashboard` (índice) e de qualquer sub-rota desconhecida
// (`/dashboard/*`) para o módulo de aterrissagem (ADR-072, Decisão 1).
//
// Preserva `location.search` deliberadamente: um `<Navigate
// to="/dashboard/inicio" replace/>` sem isso descartaria `?plant=`
// silenciosamente, quebrando link compartilhado de usina específica —
// `PlantContext` só lê a query string uma vez, na montagem.
export function DashboardIndexRedirect() {
  const location = useLocation()
  return <Navigate to={{ pathname: DASHBOARD_DEFAULT_PATH, search: location.search }} replace />
}

// URL da organização anterior (5 abas, ADR-072) → aba equivalente (ADR-083).
// Mesma regra de `?plant=`: preserva a query string.
export function LegacyModuleRedirect({ to }: { to: string }) {
  const location = useLocation()
  return <Navigate to={{ pathname: to, search: location.search }} replace />
}
