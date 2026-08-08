import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AuthProvider } from './contexts/AuthContext'
import { PlantProvider } from './contexts/PlantContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { DashboardLayout } from './pages/dashboard/DashboardLayout'
import { DashboardIndexRedirect } from './pages/dashboard/DashboardIndexRedirect'
import { FinancialPage } from './pages/dashboard/FinancialPage'
import { ProductionPage } from './pages/dashboard/ProductionPage'
import { TechnicalPage } from './pages/dashboard/TechnicalPage'
import { DASHBOARD_MODULE_SEGMENTS, DASHBOARD_ROOT_PATH } from './routes'

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          {/* Rota de layout aninhada (ADR-072, Decisão 1): `PlantProvider`
              monta uma única vez aqui, não dentro de cada rota filha — é o
              que garante que não remonta (nem refaz `GET /plants`) ao
              navegar entre módulos. */}
          <Route
            path={DASHBOARD_ROOT_PATH}
            element={
              <ProtectedRoute>
                <PlantProvider>
                  <DashboardLayout />
                </PlantProvider>
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardIndexRedirect />} />
            {/* Etapa 1 (ADR-072): a rota de Visão Geral ainda renderiza o
                `DashboardPage` atual, sem nenhuma mudança de conteúdo — a
                extração de `OverviewPage` é a etapa final da migração (Etapa
                5). Técnico (Etapa 2), Financeiro (Etapa 3) e Produção (Etapa
                4) já migraram para módulo próprio. */}
            <Route path={DASHBOARD_MODULE_SEGMENTS.overview} element={<DashboardPage />} />
            <Route path={DASHBOARD_MODULE_SEGMENTS.production} element={<ProductionPage />} />
            <Route path={DASHBOARD_MODULE_SEGMENTS.financial} element={<FinancialPage />} />
            <Route path={DASHBOARD_MODULE_SEGMENTS.technical} element={<TechnicalPage />} />
            <Route path="*" element={<DashboardIndexRedirect />} />
          </Route>
          {/* Default: redirect to dashboard (ProtectedRoute will redirect to /login if unauthenticated) */}
          <Route path="*" element={<Navigate to={DASHBOARD_ROOT_PATH} replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
