import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useAuth } from '../contexts/AuthContext'

interface ProtectedRouteProps {
  children: React.ReactNode
}

// Depois disto, a espera diz o porquê: no plano grátis o servidor hiberna e
// leva de 30 a 60 s para acordar (ADR-076).
export const SLOW_SESSION_CHECK_MS = 10_000

const BOX =
  'flex min-h-screen flex-col items-center justify-center gap-3 bg-[var(--color-surface-subtle)] px-4 text-center text-sm text-[var(--color-text-secondary)]'

function SessionCheck() {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_SESSION_CHECK_MS)
    return () => clearTimeout(timer)
  }, [])
  return (
    <div role="status" aria-live="polite" className={BOX}>
      <p className="font-medium text-[var(--color-text-primary)]">Conectando…</p>
      {slow && <p>O servidor está acordando, pode levar até um minuto.</p>}
    </div>
  )
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { status, retrySession } = useAuth()
  const location = useLocation()

  if (status === 'authenticated') return <>{children}</>

  // Nunca decide ir ao login antes de o servidor responder sobre o cookie: um
  // F5 ou link direto com sessão viva tem que continuar logado.
  if (status === 'checking') return <SessionCheck />

  if (status === 'unreachable') {
    return (
      <div role="alert" className={BOX}>
        <p className="font-medium text-[var(--color-text-primary)]">Não foi possível falar com o servidor.</p>
        <p>Verifique sua internet. Se ele estiver acordando, a próxima tentativa costuma funcionar.</p>
        <button
          type="button"
          onClick={retrySession}
          className="mt-2 inline-flex min-h-[44px] items-center justify-center rounded-[var(--radius-control)] bg-[var(--color-brand-primary)] px-5 font-semibold text-[var(--color-on-brand)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2"
        >
          Tentar de novo
        </button>
      </div>
    )
  }

  // `from` deixa o login devolver o usuário ao link profundo que ele abriu.
  // O aviso de "sessão encerrada" não vem daqui: só o AuthContext sabe se esta
  // aba teve uma sessão que acabou.
  const from = { pathname: location.pathname, search: location.search, hash: location.hash }
  return <Navigate to="/login" replace state={{ from }} />
}
