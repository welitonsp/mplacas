import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AuthProvider } from './contexts/AuthContext'
import { PlantProvider } from './contexts/PlantContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { DashboardLayout } from './pages/dashboard/DashboardLayout'
import { DashboardIndexRedirect } from './pages/dashboard/DashboardIndexRedirect'
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
            {/* Etapa 1 (ADR-072): 3 das 4 rotas de módulo ainda renderizam o
                `DashboardPage` atual, sem nenhuma mudança de conteúdo — a
                divisão em `OverviewPage`/`ProductionPage`/`FinancialPage` é
                etapa futura (Etapas 3-5). Técnico já migrou (Etapa 2, o
                menor módulo, um único recurso) para `TechnicalPage`. */}
            <Route path={DASHBOARD_MODULE_SEGMENTS.overview} element={<DashboardPage />} />
            <Route path={DASHBOARD_MODULE_SEGMENTS.production} element={<DashboardPage />} />
            <Route path={DASHBOARD_MODULE_SEGMENTS.financial} element={<DashboardPage />} />
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
