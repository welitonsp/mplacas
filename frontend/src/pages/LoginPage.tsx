import { FormEvent, useId, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../contexts/AuthContext'
import { BrandMark } from '../components/BrandMark'

const BENEFITS = [
  'Produção, consumo e economia no mesmo painel',
  'Alertas de operação com contexto técnico',
  'Dados financeiros prontos para decisão',
]

export function LoginPage() {
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const errorId = useId()

  const sessionEnded =
    (location.state as { reason?: string } | null)?.reason === 'SESSION_ENDED'

  // Redirecionamento declarativo
  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)

    if (!username.trim() || !password) {
      setError('Informe usuário e senha para continuar.')
      return
    }

    setLoading(true)
    try {
      await login(username, password)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Erro ao autenticar. Tente novamente.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[var(--color-surface-subtle)] text-[var(--color-text-primary)]">
      <main className="mx-auto grid min-h-screen w-full max-w-7xl grid-cols-1 items-center gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_26rem] lg:px-8">
        <section className="space-y-8">
          <BrandMark className="h-10 w-auto text-[var(--color-brand-primary)]" />

          <div className="max-w-3xl space-y-4">
            <p className="text-sm font-semibold uppercase tracking-wide text-[var(--color-brand-primary)]">
              Painel operacional
            </p>
            <h1 className="text-3xl font-bold leading-tight text-[var(--color-text-primary)] sm:text-5xl">
              Gestão de energia solar com leitura executiva.
            </h1>
            <p className="max-w-2xl text-lg leading-relaxed text-[var(--color-text-secondary)]">
              Acompanhe geração, perdas e retorno financeiro com uma interface preparada para operação diária.
            </p>
          </div>

          <div className="grid max-w-3xl grid-cols-1 gap-3 sm:grid-cols-3">
            {BENEFITS.map((benefit) => (
              <div
                key={benefit}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-sm"
              >
                <div className="mb-3 h-1.5 w-10 rounded-sm bg-[var(--color-energy-solar)]" />
                <p className="text-sm font-medium leading-relaxed text-[var(--color-text-secondary)]">
                  {benefit}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-lg sm:p-8">
          <div className="mb-6">
            <p className="text-sm font-semibold text-[var(--color-brand-primary)]">Acesso seguro</p>
            <h2 className="mt-1 text-2xl font-bold tracking-tight text-[var(--color-text-primary)]">
              Entrar no Mplacas
            </h2>
            <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
              Use suas credenciais operacionais para continuar.
            </p>
          </div>

          {sessionEnded && (
            <div
              role="status"
              className="mb-5 rounded-lg border border-[var(--color-danger)]/20 bg-[var(--color-danger-light)] px-4 py-3 text-sm font-medium text-[var(--color-danger-text)]"
            >
              Sua sessão foi encerrada. Entre novamente.
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            <div>
              <label htmlFor="username" className="mb-2 block text-sm font-semibold text-[var(--color-text-primary)]">
                Usuário
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                autoFocus
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={loading}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? errorId : undefined}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:border-[var(--color-brand-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-primary)]/20 disabled:opacity-50"
                placeholder="Seu usuário"
              />
            </div>

            <div>
              <label htmlFor="password" className="mb-2 block text-sm font-semibold text-[var(--color-text-primary)]">
                Senha
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? errorId : undefined}
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 pr-24 text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:border-[var(--color-brand-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-primary)]/20 disabled:opacity-50"
                  placeholder="********"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-pressed={showPassword}
                  disabled={loading}
                  className="absolute inset-y-1 right-1 flex min-w-[72px] items-center justify-center rounded-md px-3 text-xs font-semibold text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:opacity-50"
                >
                  {showPassword ? 'Ocultar' : 'Mostrar'}
                </button>
              </div>
            </div>

            {error && (
              <div
                id={errorId}
                role="alert"
                className="rounded-lg border border-[var(--color-danger)]/20 bg-[var(--color-danger-light)] px-4 py-3 text-sm font-medium text-[var(--color-danger-text)]"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="mt-2 w-full rounded-lg bg-[var(--color-brand-primary)] px-4 py-3 text-sm font-bold text-white shadow-sm transition-colors hover:bg-[var(--color-brand-primary-dark)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? 'Entrando...' : 'Entrar no painel'}
            </button>
          </form>
        </section>
      </main>
    </div>
  )
}
