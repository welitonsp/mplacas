import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AuthProvider } from './contexts/AuthContext'
import { MeProvider } from './contexts/MeContext'
import { PlantProvider } from './contexts/PlantContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import {
  DASHBOARD_MODULE_SEGMENTS,
  DASHBOARD_ROOT_PATH,
  INVITATION_PATH,
  LEGACY_MODULE_REDIRECTS,
} from './routes'

const LoginPage = lazy(() => import('./pages/LoginPage').then((module) => ({ default: module.LoginPage })))
const InvitePage = lazy(() => import('./pages/InvitePage').then((module) => ({ default: module.InvitePage })))
const PublicHomePage = lazy(() => import('./pages/PublicHomePage').then((module) => ({ default: module.default })))
const DashboardLayout = lazy(() =>
  import('./pages/dashboard/DashboardLayout').then((module) => ({ default: module.DashboardLayout }))
)
const DashboardIndexRedirect = lazy(() =>
  import('./pages/dashboard/DashboardIndexRedirect').then((module) => ({
    default: module.DashboardIndexRedirect,
  }))
)
const LegacyModuleRedirect = lazy(() =>
  import('./pages/dashboard/DashboardIndexRedirect').then((module) => ({
    default: module.LegacyModuleRedirect,
  }))
)
const OverviewPage = lazy(() =>
  import('./pages/dashboard/OverviewPage').then((module) => ({ default: module.OverviewPage }))
)
const ProductionPage = lazy(() =>
  import('./pages/dashboard/ProductionPage').then((module) => ({ default: module.ProductionPage }))
)
const FinancialPage = lazy(() =>
  import('./pages/dashboard/FinancialPage').then((module) => ({ default: module.FinancialPage }))
)
const TechnicalPage = lazy(() =>
  import('./pages/dashboard/TechnicalPage').then((module) => ({ default: module.TechnicalPage }))
)
const MethodologyPage = lazy(() =>
  import('./pages/dashboard/MethodologyPage').then((module) => ({ default: module.MethodologyPage }))
)
const ClientsPage = lazy(() =>
  import('./pages/dashboard/ClientsPage').then((module) => ({ default: module.ClientsPage }))
)
const PlantSetupPage = lazy(() =>
  import('./pages/dashboard/PlantSetupPage').then((module) => ({ default: module.PlantSetupPage }))
)

function RouteFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Carregando tela"
      className="flex min-h-screen items-center justify-center bg-[var(--color-surface-subtle)] px-4 text-sm font-medium text-[var(--color-text-secondary)]"
    >
      <span className="sr-only">Carregando tela</span>
      <span aria-hidden="true" className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 shadow-sm">
        <span className="h-2 w-2 rounded-full bg-[var(--color-brand-primary)] animate-pulse" />
        Carregando Mplacas
      </span>
    </div>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<PublicHomePage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path={INVITATION_PATH} element={<InvitePage />} />
            {/* Rota de layout aninhada (ADR-072, Decisão 1): `PlantProvider`
                monta uma única vez aqui, não dentro de cada rota filha — é o
                que garante que não remonta (nem refaz `GET /plants`) ao
                navegar entre módulos. */}
            <Route
              path={DASHBOARD_ROOT_PATH}
              element={
                <ProtectedRoute>
                  <PlantProvider>
                    <MeProvider>
                      <DashboardLayout />
                    </MeProvider>
                  </PlantProvider>
                </ProtectedRoute>
              }
            >
              <Route index element={<DashboardIndexRedirect />} />
              {/* Quatro abas, uma pergunta cada (ADR-083): Início, Energia
                  (com os detalhes técnicos dentro), Dinheiro e Minha usina. */}
              <Route path={DASHBOARD_MODULE_SEGMENTS.overview} element={<OverviewPage />} />
              <Route path={DASHBOARD_MODULE_SEGMENTS.production} element={<ProductionPage />} />
              <Route path={DASHBOARD_MODULE_SEGMENTS.technical} element={<TechnicalPage />} />
              <Route path={DASHBOARD_MODULE_SEGMENTS.financial} element={<FinancialPage />} />
              <Route path={DASHBOARD_MODULE_SEGMENTS.methodology} element={<MethodologyPage />} />
              <Route path={DASHBOARD_MODULE_SEGMENTS.setup} element={<PlantSetupPage />} />
              <Route path={DASHBOARD_MODULE_SEGMENTS.clients} element={<ClientsPage />} />
              {/* URLs da organização anterior: redirecionam, nunca 404. */}
              {LEGACY_MODULE_REDIRECTS.map(({ segment, to }) => (
                <Route key={segment} path={segment} element={<LegacyModuleRedirect to={to} />} />
              ))}
              <Route path="*" element={<DashboardIndexRedirect />} />
            </Route>
            {/* Default: redirect to dashboard (ProtectedRoute will redirect to /login if unauthenticated) */}
            <Route path="*" element={<Navigate to={DASHBOARD_ROOT_PATH} replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  )
}
