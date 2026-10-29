import { FormEvent, useEffect, useId, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../contexts/AuthContext'
import { BrandMark } from '../components/BrandMark'
import { LoadingAnnouncement } from '../components/LoadingAnnouncement'
import { warmUpApi } from '../lib/api'

const SLOW_START_HINT_MS = 6_000

// Mesmas perguntas das abas do painel (ADR-083) e o mesmo tom do Início
// ("Está tudo bem?"): o login fala com o dono da usina, não com um operador.
// Antes: "Operação diária", "Diagnóstico técnico", "leitura executiva".
const BENEFITS = [
  {
    title: 'Está tudo bem?',
    description: 'Avisa quando a usina para de mandar leitura ou gera abaixo do esperado.',
  },
  {
    title: 'Quanto gerou',
    description: 'Produção de cada dia e de cada ciclo, conferida com o que a distribuidora registrou.',
  },
  {
    title: 'Quanto economizei',
    description: 'Sua conta com e sem a usina, e o retorno do investimento comparado ao CDI.',
  },
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
  const [slowStart, setSlowStart] = useState(false)
  const errorId = useId()

  // Acorda a API assim que a tela abre (plano grátis hiberna; ver api.ts).
  useEffect(() => {
    warmUpApi()
  }, [])

  // Se a entrada passar de alguns segundos, explica o porquê em vez de deixar
  // o usuário achar que travou: quase sempre é o servidor acordando.
  useEffect(() => {
    if (!loading) {
      setSlowStart(false)
      return
    }
    const timer = setTimeout(() => setSlowStart(true), SLOW_START_HINT_MS)
    return () => clearTimeout(timer)
  }, [loading])

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
    // Sem os dois borrões decorativos (`blur-3xl`) que havia atrás do
    // formulário: ADR-077, decisão 6 — sem decoração; fundo de página liso
    // como no painel.
    <div className="relative min-h-screen overflow-hidden bg-[var(--color-surface-subtle)] text-[var(--color-text-primary)]">

      <main className="relative mx-auto grid min-h-screen w-full max-w-7xl grid-cols-1 items-center gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_27rem] lg:px-8 2xl:max-w-[96rem]">
        <section className="w-full rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[0_24px_60px_-32px_rgb(14_27_42_/_0.35)] sm:p-8 lg:order-2">
          <BrandMark className="mb-6 text-[var(--color-text-primary)] lg:hidden" />
          <div className="mb-6">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-[var(--color-brand-primary-light)] px-3 py-1 text-xs font-semibold text-[var(--color-brand-primary)]">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" aria-hidden="true" />
              Acesso protegido
            </div>
            <h1 className="text-2xl font-bold tracking-[-0.015em] text-[var(--color-text-primary)]">
              Entrar no MPlacas
            </h1>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">
              Use o usuário e a senha da sua conta.
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
                // Sem `aria-invalid` (auditoria v6, A-12): todo erro desta
                // tela vem de `login()` — credencial recusada, excesso de
                // tentativas, serviço indisponível — e nenhum deles é de
                // campo. Marcar os dois campos como inválidos anunciava ao
                // leitor de tela que ambos estavam malformados, o que é falso
                // e manda o usuário procurar defeito onde não há. A mensagem
                // segue anunciada pela região `role="alert"`, e o
                // `aria-describedby` liga o campo a ela — isso é verdadeiro.
                aria-describedby={error ? errorId : undefined}
                className="min-h-[48px] w-full rounded-[var(--radius-control)] border border-[var(--color-gray-500)] bg-[var(--color-surface)] px-4 py-3 text-[var(--color-text-primary)] outline-none transition-all duration-200 placeholder:text-[var(--color-text-secondary)] focus:border-[var(--color-brand-primary)] focus:ring-4 focus:ring-[var(--color-brand-primary)]/15 disabled:opacity-50"
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
                  // Mesma razão do campo de usuário acima (A-12).
                  aria-describedby={error ? errorId : undefined}
                  className="min-h-[48px] w-full rounded-[var(--radius-control)] border border-[var(--color-gray-500)] bg-[var(--color-surface)] px-4 py-3 pr-24 text-[var(--color-text-primary)] outline-none transition-all duration-200 placeholder:text-[var(--color-text-secondary)] focus:border-[var(--color-brand-primary)] focus:ring-4 focus:ring-[var(--color-brand-primary)]/15 disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-pressed={showPassword}
                  disabled={loading}
                  className="absolute inset-y-1 right-1 flex min-w-[72px] items-center justify-center rounded-lg px-3 text-xs font-semibold text-[var(--color-text-secondary)] transition-all duration-150 hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:opacity-50"
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
              className="mt-2 inline-flex min-h-[48px] w-full items-center justify-center gap-2 rounded-[var(--radius-control)] bg-[var(--color-brand-primary)] px-4 py-3 text-[15px] font-semibold text-[var(--color-on-brand)] transition-colors duration-150 hover:bg-[var(--color-brand-primary-dark)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none"
            >
              {loading && (
                <span
                  aria-hidden="true"
                  className="h-4 w-4 rounded-full border-2 border-current/40 border-t-current animate-spin"
                />
              )}
              {loading ? 'Entrando...' : 'Entrar no painel'}
            </button>
            <LoadingAnnouncement active={loading} message="Entrando, aguarde." />
            {loading && slowStart && (
              <p
                role="status"
                className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-4 py-3 text-center text-sm leading-6 text-[var(--color-text-secondary)]"
              >
                O sistema estava em repouso e está iniciando. Na primeira entrada do dia isso pode levar até 1 minuto.
              </p>
            )}

            <p className="text-center text-xs leading-5 text-[var(--color-text-secondary)]">
              Conexão protegida. O acesso é conferido a cada consulta aos seus dados.
            </p>
          </form>
        </section>

        {/* Proposta: depois do formulário no DOM e no celular; à esquerda só
            no desktop (`lg:order-1`). Quem abre /login quer entrar. */}
        <section className="space-y-8 lg:order-1">
          <div className="hidden items-center gap-3 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 lg:inline-flex">
            <BrandMark className="text-[var(--color-text-primary)]" />
            <span className="h-1 w-1 rounded-full bg-[var(--color-border)]" aria-hidden="true" />
            <span className="text-xs font-medium text-[var(--color-text-secondary)]">Sua usina solar</span>
          </div>

          <div className="max-w-3xl space-y-4">
            <p className="text-sm font-semibold text-[var(--color-brand-primary)]">
              Para quem tem energia solar
            </p>
            <h2 className="text-3xl font-bold leading-[1.1] tracking-[-0.02em] text-[var(--color-text-primary)] sm:text-5xl lg:text-[56px]">
              Veja quanto sua usina gera e quanto você economiza.
            </h2>
            <p className="max-w-2xl text-base leading-relaxed text-[var(--color-text-secondary)] sm:text-lg">
              A produção das placas, a fatura da distribuidora e o retorno do investimento lado a lado, com a origem de cada número à vista.
            </p>
          </div>

          <ul className="grid max-w-3xl grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-3">
            {BENEFITS.map((benefit) => (
              <li key={benefit.title} className="border-t border-[var(--color-border)] pt-4">
                <p className="text-[15px] font-semibold text-[var(--color-text-primary)]">{benefit.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-[var(--color-text-secondary)]">
                  {benefit.description}
                </p>
              </li>
            ))}
          </ul>

          {/* A "Prévia do cockpit" com Saúde 92% / Performance 87% /
              Disponibilidade 98% saiu (ADR-077): eram números inventados numa
              tela de produto que vive de dado medido. */}
        </section>
      </main>
    </div>
  )
}
