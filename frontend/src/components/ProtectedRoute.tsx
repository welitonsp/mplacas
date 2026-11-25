import { Navigate, useLocation } from 'react-router'
import { useAuth } from '../contexts/AuthContext'

interface ProtectedRouteProps {
  children: React.ReactNode
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    // `from` deixa o login devolver o usuário ao link profundo que ele abriu.
    // O aviso de "sessão encerrada" não vem mais daqui: só o AuthContext sabe
    // se esta aba teve uma sessão que acabou.
    const from = { pathname: location.pathname, search: location.search, hash: location.hash }
    return <Navigate to="/login" replace state={{ from }} />
  }

  return <>{children}</>
}
