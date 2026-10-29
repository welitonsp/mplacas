import { FormEvent, useEffect, useId, useRef, useState } from 'react'
import { deleteProviderAccount, fetchProviderAccount, saveProviderAccount } from '../lib/api'
import {
  parseProviderAccount,
  providerAccountErrorMessage,
  type ProviderAccount,
} from '../lib/dashboard/provider-account-contracts'
import { usePlantResource } from '../hooks/usePlantResource'
import { Card } from './Card'
import { LoadingAnnouncement } from './LoadingAnnouncement'
import { RetryableError } from './RetryableError'
import { SectionTitle } from './SectionTitle'

// "Conexão com o inversor" (ADR-091). É daqui que o sistema busca a produção
// da usina todo dia. Regras de segurança (skill secret-safe-ui):
// - a senha só existe no estado deste componente, nunca em storage, URL ou log;
// - o campo nunca vem preenchido e é limpo depois de salvar;
// - o servidor confere a conta na NEPViewer antes de guardar e nunca devolve
//   login completo nem senha — a tela mostra só a dica mascarada.

const INPUT_CLASS =
  'min-h-[44px] w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder-[var(--color-gray-500)] transition-colors duration-150 focus:border-[var(--color-brand-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-primary)] disabled:opacity-50 motion-reduce:transition-none'

const PRIMARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--color-brand-primary)] px-4 py-2 text-sm font-semibold text-[var(--color-on-brand)] shadow-sm transition-colors duration-200 hover:bg-[var(--color-brand-primary-dark)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

const SECONDARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-semibold text-[var(--color-text-primary)] transition-colors duration-200 hover:bg-[var(--color-surface-subtle)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

type Feedback = { tone: 'success' | 'error'; message: string } | null

function formatMoment(iso: string | null): string | null {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatusSummary({ account }: { account: ProviderAccount }) {
  if (account.status === 'SEM_CONEXAO') {
    return (
      <div>
        <p className="text-sm font-semibold text-[var(--color-text-primary)]">Nenhuma conta conectada</p>
        <p className="mt-1 text-[13px] leading-5 text-[var(--color-text-secondary)]">
          Sem a conta do inversor, o sistema não consegue buscar a produção da usina. Use o login e a senha
          do aplicativo NEPViewer.
        </p>
      </div>
    )
  }
  const lastSuccess = formatMoment(account.lastSuccessAt)
  const lastFailure = formatMoment(account.lastFailureAt)
  return (
    <div>
      <p className="text-sm font-semibold text-[var(--color-text-primary)]">
        {account.status === 'FALHA' ? 'Conectada, mas a última leitura falhou' : 'Conectada'}
        {account.loginHint && (
          <span className="font-normal text-[var(--color-text-secondary)]"> · NEPViewer, conta {account.loginHint}</span>
        )}
      </p>
      <p className="mt-1 text-[13px] leading-5 text-[var(--color-text-secondary)]">
        {account.status === 'FALHA'
          ? `A leitura de ${lastFailure ?? 'hoje'} não deu certo. Se a senha mudou no aplicativo NEPViewer, informe a nova abaixo.`
          : lastSuccess
            ? `Última leitura em ${lastSuccess}.`
            : 'A primeira leitura acontece na próxima coleta, de madrugada.'}
      </p>
    </div>
  )
}

function ConnectForm({
  plantId,
  connected,
  focusOnMount,
  onSaved,
}: {
  plantId: string
  connected: boolean
  focusOnMount: boolean
  onSaved: (message: string) => void
}) {
  const ids = useId()
  const loginId = `${ids}-login`
  const passwordId = `${ids}-password`
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
      setFeedback({ tone: 'error', message: 'Informe o login da conta NEPViewer.' })
      return
    }
    if (!password) {
      setFeedback({ tone: 'error', message: 'Informe a senha da conta NEPViewer.' })
      return
    }
    setSaving(true)
    try {
      const response = await saveProviderAccount(plantId, { login: login.trim(), password })
      if (!response.ok) {
        setFeedback({ tone: 'error', message: await providerAccountErrorMessage(response) })
        return
      }
      const account = parseProviderAccount(await response.json())
      setPassword('')
      setShowPassword(false)
      const found = account.devicesFound ?? 0
      // A mensagem sobe para a seção: o formulário fecha depois de salvar.
      onSaved(
        found === 0
          ? 'Conta conectada, mas a NEPViewer não mostra nenhum inversor nela. Confira se é a conta certa.'
          : `Conta conectada. ${found === 1 ? '1 inversor encontrado' : `${found} inversores encontrados`}.`,
      )
    } catch {
      setFeedback({ tone: 'error', message: 'Não foi possível concluir agora. Tente novamente.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5" aria-label="Conectar a conta do inversor">
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <div className="min-w-0">
          <label htmlFor={loginId} className="mb-1 block text-[13px] font-semibold text-[var(--color-text-primary)]">
            Login da NEPViewer
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
            placeholder="E-mail ou usuário do aplicativo"
            className={INPUT_CLASS}
          />
        </div>
        <div className="min-w-0">
          <label htmlFor={passwordId} className="mb-1 block text-[13px] font-semibold text-[var(--color-text-primary)]">
            Senha da NEPViewer
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
        O sistema confere a conta na NEPViewer antes de salvar. A senha fica guardada cifrada e não aparece de
        novo para ninguém.
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
        {saving ? 'Conferindo na NEPViewer...' : connected ? 'Conferir e trocar' : 'Conferir e conectar'}
      </button>
      <LoadingAnnouncement active={saving} message="Conferindo a conta na NEPViewer, aguarde." />
    </form>
  )
}

export function ProviderConnectionSection({ plantId }: { plantId: string }) {
  const resource = usePlantResource({
    plantId,
    fetcher: fetchProviderAccount,
    parse: parseProviderAccount,
    errorMessage: 'Erro ao buscar a conexão com o inversor.',
  })
  const [editing, setEditing] = useState(false)
  const [confirmingRemoval, setConfirmingRemoval] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [notice, setNotice] = useState<Feedback>(null)
  // Quando um botão some (troca aberta/fechada, confirmação, salvar), o foco
  // volta para o resumo da seção em vez de cair no <body> (WCAG 2.4.3).
  const summaryRef = useRef<HTMLDivElement>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)
  const [focusSummary, setFocusSummary] = useState(false)

  useEffect(() => {
    if (confirmingRemoval) confirmRef.current?.focus()
  }, [confirmingRemoval])

  useEffect(() => {
    if (focusSummary && summaryRef.current) {
      summaryRef.current.focus()
      setFocusSummary(false)
    }
  }, [focusSummary, resource.data])

  const account = resource.data
  const connected = account != null && account.status !== 'SEM_CONEXAO'
  const showForm = account != null && (!connected || editing)

  async function handleRemove() {
    setRemoving(true)
    setNotice(null)
    try {
      const response = await deleteProviderAccount(plantId)
      if (!response.ok) {
        const message = await providerAccountErrorMessage(response)
        setNotice({ tone: 'error', message })
        if (response.status === 404) {
          setConfirmingRemoval(false)
          resource.refetch()
        }
        return
      }
      setConfirmingRemoval(false)
      setEditing(false)
      setNotice({ tone: 'success', message: 'Conta desconectada. A produção deixa de ser buscada.' })
      setFocusSummary(true)
      resource.refetch()
    } catch {
      setNotice({ tone: 'error', message: 'Não foi possível desconectar agora. Tente novamente.' })
    } finally {
      setRemoving(false)
    }
  }

  return (
    <section id="inversor" aria-labelledby="inversor-heading" className="scroll-mt-24">
      <SectionTitle as="h2" id="inversor-heading">
        Conexão com o inversor
      </SectionTitle>
      <Card className="sm:p-6">
        <div className="space-y-5">
          {/* Fora do bloco do estado: o aviso de salvo/desconectado continua
              visível mesmo se a releitura falhar. */}
          {notice && (
            <div
              role={notice.tone === 'error' ? 'alert' : 'status'}
              className={`rounded-lg border px-3 py-2 text-sm ${
                notice.tone === 'success'
                  ? 'border-[var(--color-success)]/30 bg-[var(--color-success-light)] text-[var(--color-success-text)]'
                  : 'border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] text-[var(--color-danger-text)]'
              }`}
            >
              {notice.message}
            </div>
          )}
          {resource.error && <RetryableError message={resource.error} onRetry={resource.refetch} />}
          {!account && !resource.error && (
            <p className="text-sm text-[var(--color-text-secondary)]" role="status">
              Buscando a conexão...
            </p>
          )}
          {account && (
            <>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div ref={summaryRef} tabIndex={-1} className="rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]">
                  <StatusSummary account={account} />
                </div>
                {connected && !editing && (
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className={SECONDARY_BUTTON}
                      onClick={() => {
                        setNotice(null)
                        setConfirmingRemoval(false)
                        setEditing(true)
                      }}
                    >
                      Trocar senha ou conta
                    </button>
                    {!confirmingRemoval && (
                      <button
                        type="button"
                        className={SECONDARY_BUTTON}
                        onClick={() => {
                          setNotice(null)
                          setConfirmingRemoval(true)
                        }}
                      >
                        Desconectar
                      </button>
                    )}
                  </div>
                )}
              </div>
              {confirmingRemoval && (
                <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--color-border)] px-3 py-3">
                  <p className="text-sm text-[var(--color-text-primary)]">
                    Desconectar apaga a senha guardada e a produção deixa de ser buscada. Confirma?
                  </p>
                  <div className="flex gap-2">
                    <button
                      ref={confirmRef}
                      type="button"
                      className={PRIMARY_BUTTON}
                      onClick={handleRemove}
                      disabled={removing}
                      aria-busy={removing}
                    >
                      {removing ? 'Desconectando...' : 'Sim, desconectar'}
                    </button>
                    <button
                      type="button"
                      className={SECONDARY_BUTTON}
                      onClick={() => {
                        setConfirmingRemoval(false)
                        setFocusSummary(true)
                      }}
                      disabled={removing}
                    >
                      Cancelar
                    </button>
                  </div>
                </div>
              )}
              {showForm && (
                <>
                  <ConnectForm
                    plantId={plantId}
                    connected={connected}
                    focusOnMount={editing}
                    onSaved={(message) => {
                      setEditing(false)
                      setConfirmingRemoval(false)
                      setNotice({ tone: 'success', message })
                      setFocusSummary(true)
                      resource.refetch()
                    }}
                  />
                  {editing && (
                    <button
                      type="button"
                      className={SECONDARY_BUTTON}
                      onClick={() => {
                        setEditing(false)
                        setFocusSummary(true)
                      }}
                    >
                      Cancelar troca
                    </button>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </Card>
    </section>
  )
}
