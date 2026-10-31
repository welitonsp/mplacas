import { FormEvent, useEffect, useId, useRef, useState } from 'react'
import { PROVIDER_BRANDS, type ProviderBrand } from '../lib/dashboard/provider-account-contracts'
import { LoadingAnnouncement } from './LoadingAnnouncement'

// Escolha da marca + usuário e senha do app do celular (ADR-091/092/093).
// Usado na conexão de uma usina existente e na primeira conexão, quando a
// usina nasce da conta. Regras de segurança (skill secret-safe-ui):
// - a senha só existe no estado deste componente, nunca em storage, URL ou log;
// - o campo nunca vem preenchido e é limpo depois de enviar com sucesso;
// - mensagens de erro nunca repetem o que foi digitado.

export const INPUT_CLASS =
  'min-h-[44px] w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder-[var(--color-gray-500)] transition-colors duration-150 focus:border-[var(--color-brand-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-primary)] disabled:opacity-50 motion-reduce:transition-none'

export const PRIMARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--color-brand-primary)] px-4 py-2 text-sm font-semibold text-[var(--color-on-brand)] shadow-sm transition-colors duration-200 hover:bg-[var(--color-brand-primary-dark)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

export const SECONDARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-semibold text-[var(--color-text-primary)] transition-colors duration-200 hover:bg-[var(--color-surface-subtle)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

export interface BrandLogin {
  provider: ProviderBrand
  login: string
  password: string
}

type Feedback = { tone: 'success' | 'error'; message: string } | null

export function BrandLoginForm({
  initialBrand = 'NEPVIEWER',
  focusOnMount = false,
  submitLabel,
  ariaLabel,
  onSubmit,
}: {
  initialBrand?: ProviderBrand
  focusOnMount?: boolean
  submitLabel: string
  ariaLabel: string
  // Devolve a mensagem de erro, ou `null` quando deu certo.
  onSubmit: (credentials: BrandLogin) => Promise<string | null>
}) {
  const ids = useId()
  const loginId = `${ids}-login`
  const passwordId = `${ids}-password`
  const [brand, setBrand] = useState<ProviderBrand>(initialBrand)
  const brandInfo = PROVIDER_BRANDS.find((item) => item.value === brand) ?? PROVIDER_BRANDS[0]
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>(null)
  const loginRef = useRef<HTMLInputElement>(null)

  // Ao abrir pela troca, o foco vai para o primeiro campo (o botão que o
  // abriu some da tela).
  useEffect(() => {
    if (focusOnMount) loginRef.current?.focus()
  }, [focusOnMount])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFeedback(null)
    if (!login.trim()) {
      setFeedback({ tone: 'error', message: `Informe o usuário do app ${brandInfo.label}.` })
      return
    }
    if (!password) {
      setFeedback({ tone: 'error', message: `Informe a senha do app ${brandInfo.label}.` })
      return
    }
    setSaving(true)
    try {
      const error = await onSubmit({ provider: brand, login: login.trim(), password })
      if (error) {
        setFeedback({ tone: 'error', message: error })
        return
      }
      setPassword('')
      setShowPassword(false)
    } catch {
      setFeedback({ tone: 'error', message: 'Não foi possível concluir agora. Tente novamente.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5" aria-label={ariaLabel}>
      <fieldset>
        <legend className="mb-2 text-[13px] font-semibold text-[var(--color-text-primary)]">
          Marca do inversor
        </legend>
        <div className="flex flex-wrap gap-2">
          {PROVIDER_BRANDS.map((item) => {
            const checked = item.value === brand
            return (
              <label
                key={item.value}
                className={`inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold transition-colors duration-150 motion-reduce:transition-none focus-within:ring-2 focus-within:ring-[var(--color-brand-primary)] ${
                  checked
                    ? 'border-[var(--color-brand-primary)] bg-[var(--color-surface-subtle)] text-[var(--color-text-primary)]'
                    : 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)]'
                }`}
              >
                <input
                  type="radio"
                  name={`${ids}-brand`}
                  value={item.value}
                  checked={checked}
                  onChange={() => setBrand(item.value)}
                  disabled={saving}
                  className="h-4 w-4 accent-[var(--color-brand-primary)]"
                />
                {item.label}
              </label>
            )
          })}
        </div>
      </fieldset>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <div className="min-w-0">
          <label htmlFor={loginId} className="mb-1 block text-[13px] font-semibold text-[var(--color-text-primary)]">
            Usuário do app {brandInfo.label}
          </label>
          <input
            ref={loginRef}
            id={loginId}
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            disabled={saving}
            placeholder={`O mesmo do app ${brandInfo.app}`}
            className={INPUT_CLASS}
          />
        </div>
        <div className="min-w-0">
          <label htmlFor={passwordId} className="mb-1 block text-[13px] font-semibold text-[var(--color-text-primary)]">
            Senha do app {brandInfo.label}
          </label>
          <div className="relative">
            <input
              id={passwordId}
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={saving}
              className={`${INPUT_CLASS} pr-32`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              aria-controls={passwordId}
              disabled={saving}
              className="absolute inset-y-0 right-0 flex min-h-[44px] min-w-[112px] items-center justify-center rounded-lg px-3 text-xs font-semibold text-[var(--color-text-secondary)] transition-colors duration-150 hover:bg-[var(--color-surface-subtle)] hover:text-[var(--color-text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:opacity-50 motion-reduce:transition-none"
            >
              {showPassword ? 'Ocultar senha' : 'Mostrar senha'}
            </button>
          </div>
        </div>
      </div>
      <p className="text-xs leading-5 text-[var(--color-text-secondary)]">
        O sistema confere a conta na {brandInfo.label} antes de salvar. A senha fica guardada cifrada e não
        aparece de novo para ninguém.
      </p>
      {feedback && (
        <div
          role={feedback.tone === 'error' ? 'alert' : 'status'}
          className={`rounded-lg border px-3 py-2 text-sm ${
            feedback.tone === 'success'
              ? 'border-[var(--color-success)]/30 bg-[var(--color-success-light)] text-[var(--color-success-text)]'
              : 'border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] text-[var(--color-danger-text)]'
          }`}
        >
          {feedback.message}
        </div>
      )}
      <button type="submit" className={PRIMARY_BUTTON} disabled={saving} aria-busy={saving}>
        {saving ? `Conferindo na ${brandInfo.label}...` : submitLabel}
      </button>
      <LoadingAnnouncement active={saving} message={`Conferindo a conta na ${brandInfo.label}, aguarde.`} />
    </form>
  )
}

