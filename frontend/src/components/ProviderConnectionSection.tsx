import { useEffect, useRef, useState } from 'react'
import { deleteProviderAccount, fetchProviderAccount, saveProviderAccount } from '../lib/api'
import {
  brandLabel,
  parseProviderAccount,
  providerAccountErrorMessage,
  type ProviderAccount,
  type ProviderBrand,
} from '../lib/dashboard/provider-account-contracts'
import { usePlantResource } from '../hooks/usePlantResource'
import { Card } from './Card'
import { BrandLoginForm, PRIMARY_BUTTON, SECONDARY_BUTTON, type BrandLogin } from './BrandLoginForm'
import { RetryableError } from './RetryableError'
import { SectionTitle } from './SectionTitle'

// "Conexão com o inversor" (ADR-091). É daqui que o sistema busca a produção
// da usina todo dia. Regras de segurança (skill secret-safe-ui):
// - a senha só existe no estado deste componente, nunca em storage, URL ou log;
// - o campo nunca vem preenchido e é limpo depois de salvar;
// - o cliente escolhe a marca (NEPViewer ou Growatt, ADR-092) e digita o mesmo
//   usuário e senha do app do celular;
// - o servidor confere a conta no fabricante antes de guardar e nunca devolve
//   login completo nem senha — a tela mostra só a dica mascarada.

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
          Sem a conta do inversor, o sistema não consegue buscar a produção da usina. Escolha a marca e use o
          mesmo usuário e senha do aplicativo do celular.
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
          <span className="font-normal text-[var(--color-text-secondary)]">
            {' '}
            · {brandLabel(account.provider)}, conta {account.loginHint}
          </span>
        )}
      </p>
      <p className="mt-1 text-[13px] leading-5 text-[var(--color-text-secondary)]">
        {account.status === 'FALHA'
          ? `A leitura de ${lastFailure ?? 'hoje'} não deu certo. Se a senha mudou no aplicativo ${brandLabel(account.provider)}, informe a nova abaixo.`
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
  initialBrand,
  focusOnMount,
  onSaved,
}: {
  plantId: string
  connected: boolean
  initialBrand: ProviderBrand
  focusOnMount: boolean
  onSaved: (message: string) => void
}) {
  async function submit(credentials: BrandLogin): Promise<string | null> {
    const label = brandLabel(credentials.provider)
    const response = await saveProviderAccount(plantId, credentials)
    if (!response.ok) return providerAccountErrorMessage(response, credentials.provider)
    const account = parseProviderAccount(await response.json())
    const found = account.devicesFound ?? 0
    // A mensagem sobe para a seção: o formulário fecha depois de salvar.
    onSaved(
      found === 0
        ? `Conta conectada, mas a ${label} não mostra nenhuma usina ou inversor nela. Confira se é a conta certa.`
        : credentials.provider === 'GROWATT'
          ? `Conta conectada. ${found === 1 ? '1 usina encontrada' : `${found} usinas encontradas`} na Growatt.`
          : `Conta conectada. ${found === 1 ? '1 inversor encontrado' : `${found} inversores encontrados`}.`,
    )
    return null
  }

  return (
    <BrandLoginForm
      initialBrand={initialBrand}
      focusOnMount={focusOnMount}
      ariaLabel="Conectar a conta do inversor"
      submitLabel={connected ? 'Conferir e trocar' : 'Conferir e conectar'}
      onSubmit={submit}
    />
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
        const message = await providerAccountErrorMessage(response, account?.provider ?? null)
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
                    initialBrand={account.provider === 'GROWATT' ? 'GROWATT' : 'NEPVIEWER'}
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
