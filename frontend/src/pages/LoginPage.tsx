import { FormEvent, useId, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../contexts/AuthContext'
import { BrandMark } from '../components/BrandMark'

const BENEFITS = [
  'Produção e consumo consolidados',
  'Diagnósticos com ações recomendadas',
  'Indicadores financeiros auditáveis',
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

  // Redirecionamento declarativo — evitar `navigate()` durante o render, que é
  // um efeito colateral inválido nesse ponto do ciclo de vida do componente.
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
      // Display safe error messages only — no stack traces or internal details
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
    <div className="min-h-screen grid lg:grid-cols-2 bg-gray-50">
      {/* Painel decorativo — some em telas pequenas, só a marca reduzida
          permanece visível acima do formulário. */}
      <div className="hidden lg:flex flex-col justify-center px-16 py-12 bg-gradient-to-br from-[var(--color-brand-primary)] to-[var(--color-brand-primary-dark)] text-white">
        <BrandMark className="h-10 w-auto text-white" />
        <h2 className="mt-10 text-3xl font-semibold leading-tight">
          Energia solar explicada com dados auditáveis.
        </h2>
        <p className="mt-4 text-base text-white/80 max-w-md">
          Acompanhe a operação da sua usina com indicadores claros e
          rastreáveis, do painel à conta de luz.
        </p>
        <ul className="mt-8 space-y-3">
          {BENEFITS.map((benefit) => (
            <li key={benefit} className="flex items-center gap-2 text-sm text-white/90">
              <svg
                aria-hidden="true"
                viewBox="0 0 20 20"
                className="h-5 w-5 flex-shrink-0"
                fill="none"
              >
                <circle cx="10" cy="10" r="9" stroke="currentColor" strokeWidth="1.5" />
                <path d="M6 10.5l2.5 2.5L14 7.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {benefit}
            </li>
          ))}
        </ul>
      </div>

      <div className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex justify-center lg:hidden">
            <BrandMark className="h-8 w-auto text-[var(--color-brand-primary)]" />
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
            <div className="mb-8 text-center">
              <h1 className="text-2xl font-semibold text-gray-900 hidden lg:block">Mplacas</h1>
              <p className="mt-1 text-sm text-gray-500">Acesse sua conta para continuar</p>
            </div>

            {sessionEnded && (
              <div
                role="status"
                className="mb-4 rounded-lg bg-gray-100 border border-gray-200 px-3 py-2 text-sm text-gray-700"
              >
                Sua sessão foi encerrada. Entre novamente.
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-4">
              <div>
                <label
                  htmlFor="username"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
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
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-500 transition-colors duration-150 focus:border-[var(--color-brand-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-primary)] focus-visible:ring-2 disabled:opacity-50"
                  placeholder="seu.usuario"
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
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
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 pr-16 text-sm text-gray-900 placeholder-gray-500 transition-colors duration-150 focus:border-[var(--color-brand-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-primary)] focus-visible:ring-2 disabled:opacity-50"
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    aria-pressed={showPassword}
                    disabled={loading}
                    className="absolute inset-y-0 right-0 flex items-center justify-center min-w-[44px] px-3 text-xs font-medium text-gray-600 hover:text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] rounded-r-lg disabled:opacity-50"
                  >
                    {showPassword ? 'Ocultar' : 'Mostrar'}
                  </button>
                </div>
              </div>

              {error && (
                <div
                  id={errorId}
                  role="alert"
                  className="rounded-lg bg-[var(--color-danger-light)] border border-[var(--color-danger)]/30 px-3 py-2 text-sm text-[var(--color-danger)]"
                >
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-lg bg-[var(--color-brand-primary)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-brand-primary-dark)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-primary)] focus:ring-offset-2 focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150"
              >
                {loading ? 'Entrando...' : 'Entrar'}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
