import { FormEvent, useEffect, useId, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { BrandMark } from '../components/BrandMark'
import { LoadingAnnouncement } from '../components/LoadingAnnouncement'
import { useAuth } from '../contexts/AuthContext'
import { acceptInvitation, inspectInvitation, warmUpApi } from '../lib/api'
import {
  INVITATION_MAX_PASSWORD,
  INVITATION_MIN_PASSWORD,
  parseInvitationPreview,
  readInvitationToken,
  type InvitationPreview,
} from '../lib/dashboard/onboarding-contracts'
import { DASHBOARD_ROOT_PATH } from '../routes'

// Convite de cliente (ADR-093). O dono manda o link `/convite#token=...`; o
// cliente cria a senha e já entra — a primeira tela do painel é a conexão
// com a marca do inversor, que cria a usina.
//
// Segurança:
// - o token vem no fragmento (`#`), que nunca vai ao servidor nem ao
//   `Referer`, e é tirado da barra de endereço assim que lido;
// - token e senha ficam só no estado deste componente;
// - a senha mínima é conferida aqui: o 422 do servidor repetiria o digitado.

type Stage =
  | { kind: 'loading' }
  | { kind: 'invalid'; message: string }
  | { kind: 'ready'; preview: InvitationPreview }

const INVALID = 'Este convite não vale mais: pode ter vencido ou já ter sido usado. Peça um novo a quem enviou.'

const FIELD =
  'min-h-[48px] w-full rounded-[var(--radius-control)] border border-[var(--color-gray-500)] bg-[var(--color-surface)] px-4 py-3 text-[var(--color-text-primary)] outline-none transition-all duration-200 focus:border-[var(--color-brand-primary)] focus:ring-4 focus:ring-[var(--color-brand-primary)]/15 disabled:opacity-50 motion-reduce:transition-none'

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function InvitePage() {
  const { adoptSession } = useAuth()
  const navigate = useNavigate()
  // Lido uma vez só, na primeira renderização: o efeito pode rodar duas vezes
  // em desenvolvimento, e na segunda o fragmento já foi apagado. Fica só aqui
  // (não em estado) e é zerado depois do aceite.
  const tokenRef = useRef<string | null | undefined>(undefined)
  if (tokenRef.current === undefined) tokenRef.current = readInvitationToken(window.location.hash)
  const [stage, setStage] = useState<Stage>({ kind: 'loading' })
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const passwordId = useId()
  const confirmId = useId()
  const hintId = useId()
  const errorId = useId()

  useEffect(() => {
    warmUpApi()
    const token = tokenRef.current
    // Tira o token da barra de endereço (e do histórico) logo depois de ler.
    if (window.location.hash) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
    }
    if (!token) {
      setStage({ kind: 'invalid', message: 'O link do convite está incompleto. Abra de novo o link que você recebeu.' })
      return
    }
    let cancelled = false
    async function inspect(value: string) {
      try {
        const response = await inspectInvitation(value)
        if (cancelled) return
        if (response.status === 429) {
          setStage({ kind: 'invalid', message: 'Muitas tentativas. Espere alguns minutos e abra o link de novo.' })
          return
        }
        if (!response.ok) {
          setStage({ kind: 'invalid', message: INVALID })
          return
        }
        setStage({ kind: 'ready', preview: parseInvitationPreview(await response.json()) })
      } catch {
        if (!cancelled) {
          setStage({
            kind: 'invalid',
            message: 'Não foi possível abrir o convite agora. Verifique a internet e abra o link de novo.',
          })
        }
      }
    }
    void inspect(token)
    return () => {
      cancelled = true
    }
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (stage.kind !== 'ready' || !tokenRef.current) return
    // Conta caracteres como o servidor (um emoji vale 1, não 2).
    const length = [...password].length
    if (length < INVITATION_MIN_PASSWORD) {
      setError(`A senha precisa ter pelo menos ${INVITATION_MIN_PASSWORD} caracteres.`)
      return
    }
    if (length > INVITATION_MAX_PASSWORD) {
      setError(`A senha pode ter no máximo ${INVITATION_MAX_PASSWORD} caracteres.`)
      return
    }
    if (password !== confirm) {
      setError('As duas senhas não são iguais.')
      return
    }
    setSaving(true)
    try {
      const response = await acceptInvitation(tokenRef.current, password)
      if (response.status === 429) {
        setError('Muitas tentativas. Espere alguns minutos e tente de novo.')
        return
      }
      if (response.status === 400) {
        setStage({ kind: 'invalid', message: INVALID })
        return
      }
      if (response.status === 422) {
        setError(
          `O servidor não aceitou esta senha. Use entre ${INVITATION_MIN_PASSWORD} e ${INVITATION_MAX_PASSWORD} caracteres.`,
        )
        return
      }
      if (!response.ok) {
        // Falha nossa (5xx): o convite continua valendo, pode tentar de novo.
        setError('O sistema não conseguiu concluir agora. Seu convite continua valendo: tente de novo em instantes.')
        return
      }
      const body = (await response.json()) as { access_token?: unknown; refresh_token?: unknown }
      if (typeof body.access_token !== 'string' || typeof body.refresh_token !== 'string') {
        setError('Resposta inesperada do servidor. Tente entrar pela tela de login.')
        return
      }
      tokenRef.current = null
      setPassword('')
      setConfirm('')
      adoptSession(body.access_token, body.refresh_token, stage.preview.username)
      navigate(DASHBOARD_ROOT_PATH, { replace: true })
    } catch {
      setError('Não foi possível concluir agora. Verifique a internet e tente de novo.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-[var(--color-surface-subtle)] text-[var(--color-text-primary)]">
      <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-4 py-10">
        <section className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[0_24px_60px_-32px_rgb(14_27_42_/_0.35)] sm:p-8">
          <BrandMark className="mb-6 text-[var(--color-text-primary)]" />
          {stage.kind === 'loading' && (
            <p role="status" className="text-sm text-[var(--color-text-secondary)]">
              Abrindo o convite...
            </p>
          )}
          {stage.kind === 'invalid' && (
            <div>
              <h1 className="text-2xl font-bold tracking-[-0.015em]">Convite indisponível</h1>
              <p role="alert" className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">
                {stage.message}
              </p>
              <Link
                to="/login"
                className="mt-6 inline-flex min-h-[44px] items-center text-sm font-semibold text-[var(--color-brand-primary)] underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
              >
                Já tenho senha: entrar
              </Link>
            </div>
          )}
          {stage.kind === 'ready' && (
            <>
              <h1 className="text-2xl font-bold tracking-[-0.015em]">Crie sua senha</h1>
              <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">
                Você foi convidado para acompanhar <strong>{stage.preview.organizationName}</strong> no MPlacas.
                Seu usuário é <strong className="break-all">{stage.preview.username}</strong>.
              </p>
              <form onSubmit={handleSubmit} noValidate className="mt-6 space-y-5">
                {/* Usuário oculto para o gerenciador de senhas salvar o par certo. */}
                <input
                  type="text"
                  name="username"
                  autoComplete="username"
                  value={stage.preview.username}
                  readOnly
                  tabIndex={-1}
                  aria-hidden="true"
                  className="sr-only"
                />
                <div>
                  <label htmlFor={passwordId} className="mb-2 block text-sm font-semibold">
                    Nova senha
                  </label>
                  <div className="relative">
                    <input
                      id={passwordId}
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      autoFocus
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      disabled={saving}
                      aria-describedby={error ? `${hintId} ${errorId}` : hintId}
                      className={`${FIELD} pr-32`}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((prev) => !prev)}
                      aria-controls={passwordId}
                      disabled={saving}
                      className="absolute inset-y-[2px] right-1 flex min-w-[112px] items-center justify-center rounded-lg px-3 text-xs font-semibold text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-subtle)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:opacity-50"
                    >
                      {showPassword ? 'Ocultar senha' : 'Mostrar senha'}
                    </button>
                  </div>
                  <p id={hintId} className="mt-1 text-xs text-[var(--color-text-secondary)]">
                    Pelo menos {INVITATION_MIN_PASSWORD} caracteres. Uma frase curta fácil de lembrar serve.
                  </p>
                </div>
                <div>
                  <label htmlFor={confirmId} className="mb-2 block text-sm font-semibold">
                    Repita a senha
                  </label>
                  <input
                    id={confirmId}
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    disabled={saving}
                    aria-describedby={error ? errorId : undefined}
                    className={FIELD}
                  />
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
                  disabled={saving}
                  aria-busy={saving}
                  className="inline-flex min-h-[48px] w-full items-center justify-center rounded-[var(--radius-control)] bg-[var(--color-brand-primary)] px-4 py-3 text-sm font-semibold text-[var(--color-on-brand)] transition-colors duration-150 hover:bg-[var(--color-brand-primary-dark)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none"
                >
                  {saving ? 'Criando...' : 'Criar senha e entrar'}
                </button>
                <LoadingAnnouncement active={saving} message="Criando sua senha, aguarde." />
                <p className="text-center text-xs text-[var(--color-text-secondary)]">
                  Convite válido até {formatDate(stage.preview.expiresAt)}.
                </p>
              </form>
            </>
          )}
        </section>
      </main>
    </div>
  )
}
