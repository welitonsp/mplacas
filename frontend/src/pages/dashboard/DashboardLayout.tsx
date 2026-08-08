import { Outlet } from 'react-router'
import { AppShell } from '../../components/AppShell'
import { DashboardNav } from '../../components/DashboardNav'

// Rota de layout dos módulos do painel (ADR-072, Decisão 1). `AppShell` já
// renderiza `AppHeader`; aqui só precisamos entregar o `DashboardNav` no slot
// `subnav` e o conteúdo do módulo ativo via `<Outlet/>`. `PlantProvider` NÃO
// entra aqui — ele envolve esta rota em `App.tsx`, uma única vez, para não
// remontar (e refazer `GET /plants`) a cada troca de módulo.
export function DashboardLayout() {
  return (
    <AppShell subnav={<DashboardNav />}>
      <Outlet />
    </AppShell>
  )
}
