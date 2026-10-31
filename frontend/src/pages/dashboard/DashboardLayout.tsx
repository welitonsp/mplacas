import { lazy, Suspense } from 'react'
import { Outlet, useLocation } from 'react-router'
import { AppShell } from '../../components/AppShell'
import { DashboardNav } from '../../components/DashboardNav'
import { useMe } from '../../contexts/MeContext'
import { usePlant } from '../../contexts/PlantContext'
import { DASHBOARD_CLIENTS_PATH } from '../../routes'

// Só quem ainda não tem usina vê estas telas: carregadas sob demanda, fora do
// custo de todo acesso ao painel.
const FirstConnectionPanel = lazy(() =>
  import('../../components/FirstConnectionPanel').then((module) => ({ default: module.FirstConnectionPanel })),
)
const NoPlantReadOnly = lazy(() =>
  import('../../components/FirstConnectionPanel').then((module) => ({ default: module.NoPlantReadOnly })),
)

// Rota de layout dos módulos do painel (ADR-072, Decisão 1). `AppShell` já
// renderiza `AppHeader`; aqui só precisamos entregar o `DashboardNav` no slot
// `subnav` e o conteúdo do módulo ativo via `<Outlet/>`. `PlantProvider` NÃO
// entra aqui — ele envolve esta rota em `App.tsx`, uma única vez, para não
// remontar (e refazer `GET /plants`) a cada troca de módulo.
//
// Conta sem usina (cliente recém-convidado, ADR-093 § 7): no lugar do módulo
// aparece a primeira conexão — o cliente conecta a conta da marca e a usina
// nasce dela. Quem só lê vê um aviso. "Clientes" do dono não depende de usina.
export function DashboardLayout() {
  const { plants, loading, error } = usePlant()
  const { me, loading: meLoading } = useMe()
  const { pathname } = useLocation()
  const withoutPlant =
    !loading && !error && plants.length === 0 && !pathname.startsWith(DASHBOARD_CLIENTS_PATH)

  return (
    <AppShell subnav={<DashboardNav />}>
      {withoutPlant ? (
        <Suspense fallback={<p role="status" className="text-sm text-[var(--color-text-secondary)]">Carregando...</p>}>
          {/* Formulário de escrita só para ADMIN confirmado; sem "quem sou eu"
              (carregando ou falhou), modo restrito. */}
          {meLoading ? (
            <p role="status" className="text-sm text-[var(--color-text-secondary)]">
              Carregando...
            </p>
          ) : me?.role === 'ADMIN' ? (
            <FirstConnectionPanel />
          ) : (
            <NoPlantReadOnly />
          )}
        </Suspense>
      ) : (
        <Outlet />
      )}
    </AppShell>
  )
}
