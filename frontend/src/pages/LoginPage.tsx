import { FormEvent, useId, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../contexts/AuthContext'
import { BrandMark } from '../components/BrandMark'
import { LoadingAnnouncement } from '../components/LoadingAnnouncement'

const BENEFITS = [
  {
    title: 'Operação diária',
    description: 'Produção, consumo e economia no mesmo painel.',
  },
  {
    title: 'Diagnóstico técnico',
    description: 'Alertas de operação com contexto de causa provável.',
  },
  {
    title: 'Decisão financeira',
    description: 'Economia, tarifa, ROI e payback prontos para leitura executiva.',
  },
]

const PREVIEW_METRICS = [
  { label: 'Saúde', value: '92%', tone: 'success', width: '92%' },
  { label: 'Performance', value: '87%', tone: 'brand', width: '87%' },
  { label: 'Disponibilidade', value: '98%', tone: 'success', width: '98%' },
]

const TONE_CLASS: Record<string, { bar: string; text: string }> = {
  brand: { bar: 'bg-[var(--color-brand-primary)]', text: 'text-[var(--color-brand-primary)]' },
  success: { bar: 'bg-[var(--color-success)]', text: 'text-[var(--color-success-text)]' },
}

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
    <div className="relative min-h-screen overflow-hidden bg-[var(--color-surface-subtle)] text-[var(--color-text-primary)]">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-32 top-[-18rem] h-[34rem] w-[34rem] rounded-full bg-[var(--color-brand-primary)]/10 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute bottom-[-16rem] right-[-10rem] h-[32rem] w-[32rem] rounded-full bg-[var(--color-energy-solar)]/15 blur-3xl"
      />

      <main className="relative mx-auto grid min-h-screen w-full max-w-7xl grid-cols-1 items-center gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_27rem] lg:px-8 2xl:max-w-[96rem]">
        <section className="space-y-8">
          <div className="inline-flex items-center gap-3 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)]/80 px-3 py-2 shadow-sm backdrop-blur">
            <BrandMark className="h-8 w-auto text-[var(--color-brand-primary)]" />
            <span className="text-sm font-semibold text-[var(--color-text-primary)]">Mplacas</span>
            <span className="h-1 w-1 rounded-full bg-[var(--color-border)]" aria-hidden="true" />
            <span className="text-xs font-medium text-[var(--color-text-secondary)]">Cockpit solar</span>
          </div>

          <div className="max-w-3xl space-y-4">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--color-brand-primary)]">
              Painel operacional
            </p>
            <h1 className="text-4xl font-bold leading-tight tracking-tight text-[var(--color-text-primary)] sm:text-5xl lg:text-6xl">
              Gestão de energia solar com leitura executiva.
            </h1>
            <p className="max-w-2xl text-lg leading-relaxed text-[var(--color-text-secondary)]">
              Entre em um painel preparado para explicar geração, perdas, retorno financeiro e disponibilidade sem exigir garimpo de dados.
            </p>
          </div>

          <div className="grid max-w-3xl grid-cols-1 gap-3 sm:grid-cols-3">
            {BENEFITS.map((benefit) => (
              <div
                key={benefit.title}
                className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]/85 p-4 shadow-sm backdrop-blur transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md motion-reduce:transition-none"
              >
                <div className="mb-3 h-1.5 w-10 rounded-full bg-[var(--color-energy-solar)] shadow-[0_0_0_3px_var(--color-energy-solar-light)]" />
                <p className="text-sm font-semibold text-[var(--color-text-primary)]">{benefit.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-[var(--color-text-secondary)]">
                  {benefit.description}
                </p>
              </div>
            ))}
          </div>

          <aside className="max-w-3xl rounded-3xl border border-[var(--color-border)] bg-[var(--color-surface)]/80 p-4 shadow-[var(--shadow-cockpit)] backdrop-blur">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-brand-primary)]">
                  Prévia do cockpit
                </p>
                <p className="mt-1 text-lg font-bold text-[var(--color-text-primary)]">
                  Operação, técnica e financeiro no mesmo olhar
                </p>
              </div>
              <span className="rounded-full bg-[var(--color-success-light)] px-3 py-1 text-xs font-semibold text-[var(--color-success-text)]">
                Interface executiva
              </span>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {PREVIEW_METRICS.map((metric) => {
                const tone = TONE_CLASS[metric.tone]
                return (
                  <div key={metric.label} className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 shadow-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-[var(--color-text-secondary)]">{metric.label}</span>
                      <span className={`text-sm font-bold tabular-nums ${tone.text}`}>{metric.value}</span>
                    </div>
                    <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--color-chart-track)] shadow-inner" aria-hidden="true">
                      <div
                        className={`h-full rounded-full ${tone.bar}`}
                        style={{ width: metric.width }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </aside>
        </section>

        <section className="w-full rounded-3xl border border-[var(--color-border)] bg-[var(--color-surface)]/95 p-6 shadow-[var(--shadow-cockpit)] backdrop-blur sm:p-8">
          <div className="mb-6">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-[var(--color-brand-primary-light)] px-3 py-1 text-xs font-semibold text-[var(--color-brand-primary)]">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" aria-hidden="true" />
              Acesso protegido
            </div>
            <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)]">
              Entrar no Mplacas
            </h2>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">
              Use suas credenciais operacionais para abrir o painel da usina.
            </p>
          </div>

          {sessionEnded && (
            <div
              role="status"
              className="mb-5 rounded-2xl border border-[var(--color-danger)]/20 bg-[var(--color-danger-light)] px-4 py-3 text-sm font-medium text-[var(--color-danger-text)]"
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
                className="w-full rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-[var(--color-text-primary)] shadow-sm outline-none transition-all duration-200 placeholder:text-[var(--color-text-secondary)] focus:border-[var(--color-brand-primary)] focus:ring-4 focus:ring-[var(--color-brand-primary)]/15 disabled:opacity-50"
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
                  className="w-full rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 pr-24 text-[var(--color-text-primary)] shadow-sm outline-none transition-all duration-200 placeholder:text-[var(--color-text-secondary)] focus:border-[var(--color-brand-primary)] focus:ring-4 focus:ring-[var(--color-brand-primary)]/15 disabled:opacity-50"
                  placeholder="********"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-pressed={showPassword}
                  disabled={loading}
                  className="absolute inset-y-1 right-1 flex min-w-[72px] items-center justify-center rounded-xl px-3 text-xs font-semibold text-[var(--color-text-secondary)] transition-all duration-150 hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:opacity-50"
                >
                  {showPassword ? 'Ocultar' : 'Mostrar'}
                </button>
              </div>
            </div>

            {error && (
              <div
                id={errorId}
                role="alert"
                className="rounded-2xl border border-[var(--color-danger)]/20 bg-[var(--color-danger-light)] px-4 py-3 text-sm font-medium text-[var(--color-danger-text)]"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              aria-busy={loading}
              className="mt-2 inline-flex min-h-[48px] w-full items-center justify-center gap-2 rounded-2xl bg-[var(--color-brand-primary)] px-4 py-3 text-sm font-bold text-white shadow-[0_18px_36px_-20px_var(--color-brand-primary)] transition-all duration-200 hover:-translate-y-0.5 hover:bg-[var(--color-brand-primary-dark)] hover:shadow-[0_22px_44px_-22px_var(--color-brand-primary)] active:translate-y-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 motion-reduce:transition-none"
            >
              {loading && (
                <span
                  aria-hidden="true"
                  className="h-4 w-4 rounded-full border-2 border-white/45 border-t-white animate-spin"
                />
              )}
              {loading ? 'Entrando...' : 'Entrar no painel'}
            </button>
            <LoadingAnnouncement active={loading} message="Entrando, aguarde." />

            <p className="text-center text-xs leading-5 text-[var(--color-text-secondary)]">
              Sessão protegida por credenciais operacionais. O backend valida permissões a cada requisição.
            </p>
          </form>
        </section>
      </main>
    </div>
  )
}
