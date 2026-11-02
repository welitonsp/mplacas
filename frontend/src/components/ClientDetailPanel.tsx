import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchClient, reinviteClient, resetClientAccess, setClientActive } from '../lib/api'
import {
  clientErrorMessage,
  describeActivity,
  parseClientDetail,
  parseClientInvitation,
  STAGE_COPY,
  type ClientDetail,
  type ClientInvitation,
  type ClientStage,
} from '../lib/dashboard/clients-contracts'
import { brandLabel } from '../lib/dashboard/provider-account-contracts'
import { PRIMARY_BUTTON, SECONDARY_BUTTON } from './BrandLoginForm'
import { Card } from './Card'
import { RetryableError } from './RetryableError'

// Ficha do cliente (ADR-095): em que etapa ele está, o que tem conectado, o
// que aconteceu (histórico) e as ações do dono — novo convite, redefinir
// acesso, desativar/reativar. A etapa e o histórico vêm prontos do backend.

const TONES: Record<string, string> = {
  neutral: 'bg-[var(--color-gray-100)] text-[var(--color-text-secondary)]',
  progress: 'bg-[var(--color-brand-primary-light)] text-[var(--color-brand-primary)]',
  ok: 'bg-[var(--color-success-light)] text-[var(--color-success-text)]',
  warn: 'bg-[var(--color-warning-light)] text-[var(--color-warning-text)]',
  off: 'bg-[var(--color-gray-100)] text-[var(--color-text-secondary)] line-through',
}

export function StageBadge({ stage }: { stage: ClientStage }) {
  const copy = STAGE_COPY[stage]
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[copy.tone]}`}>
      {copy.label}
    </span>
  )
}

export function formatMoment(iso: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-[var(--color-text-secondary)]">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-[var(--color-text-primary)]">{value}</dd>
    </div>
  )
}

export function ClientDetailPanel({
  organizationId,
  onBack,
  onLink,
  onChanged,
}: {
  organizationId: string
  onBack: () => void
  // Link de uso único gerado (convite ou redefinição): a página mostra para copiar.
  onLink: (name: string, invitation: ClientInvitation, purpose: 'INVITE' | 'RESET') => void
  onChanged: () => void
}) {
  const [detail, setDetail] = useState<ClientDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [confirmingDeactivate, setConfirmingDeactivate] = useState(false)
  const headingRef = useRef<HTMLHeadingElement>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const response = await fetchClient(organizationId)
      if (!response.ok) {
        setError(await clientErrorMessage(response))
        return
      }
      setDetail(parseClientDetail(await response.json()))
    } catch {
      setError('Erro ao abrir a ficha do cliente.')
    }
  }, [organizationId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (detail) headingRef.current?.focus()
    // foco só na primeira carga da ficha
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.organizationId])

  async function run(kind: string, action: () => Promise<Response>, after: (response: Response) => Promise<void>) {
    setBusy(kind)
    setNotice(null)
    try {
      const response = await action()
      if (!response.ok) {
        setNotice(await clientErrorMessage(response))
        return
      }
      await after(response)
      onChanged()
      await load()
    } catch {
      setNotice('Não foi possível concluir agora. Tente novamente.')
    } finally {
      setBusy(null)
    }
  }

  const backButton = (
    <button type="button" className={SECONDARY_BUTTON} onClick={onBack}>
      <span aria-hidden="true">←</span> Voltar para clientes
    </button>
  )

  if (error) {
    return (
      <div className="space-y-4">
        {backButton}
        <RetryableError message={error} onRetry={() => void load()} />
      </div>
    )
  }
  if (!detail) {
    return (
      <div className="space-y-4">
        {backButton}
        <p role="status" className="text-sm text-[var(--color-text-secondary)]">
          Abrindo a ficha...
        </p>
      </div>
    )
  }

  const plant = detail.plants[0]
  const connection = detail.connection
  return (
    <div className="space-y-6">
      {backButton}
      <Card className="sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2
              ref={headingRef}
              tabIndex={-1}
              className="font-display text-xl font-semibold text-[var(--color-text-primary)] focus:outline-none"
            >
              {detail.name}
            </h2>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{detail.adminUsername ?? 'sem e-mail'}</p>
          </div>
          <StageBadge stage={detail.stage} />
        </div>
        <dl className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Cliente desde" value={formatMoment(detail.createdAt)} />
          <Field
            label="Usina"
            value={plant ? `${plant.name}${plant.installedPowerKwp ? ` · ${Number(plant.installedPowerKwp).toLocaleString('pt-BR')} kWp` : ''}` : 'Ainda não criada'}
          />
          <Field label="Marca" value={connection ? brandLabel(connection.provider) : 'Não conectada'} />
          <Field label="Última leitura" value={connection ? formatMoment(connection.lastSuccessAt) : '—'} />
          <Field
            label="Última falha"
            value={connection?.lastFailureAt ? `${formatMoment(connection.lastFailureAt)}${connection.lastFailureCode ? ` (${connection.lastFailureCode})` : ''}` : '—'}
          />
          <Field
            label="Link pendente"
            value={
              detail.pendingLink
                ? `${detail.pendingLink.purpose === 'RESET' ? 'Redefinir acesso' : 'Convite'}, vale até ${formatMoment(detail.pendingLink.expiresAt)}`
                : 'Nenhum'
            }
          />
        </dl>
      </Card>

      <section aria-labelledby="client-actions-heading">
        <h3 id="client-actions-heading" className="mb-3 text-base font-semibold text-[var(--color-text-primary)]">
          Ações
        </h3>
        <Card className="sm:p-6">
          <div className="space-y-4">
            {notice && (
              <div role="alert" className="rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] px-3 py-2 text-sm text-[var(--color-danger-text)]">
                {notice}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              {detail.active && detail.hasUser && (
                <button
                  type="button"
                  className={PRIMARY_BUTTON}
                  disabled={busy !== null}
                  aria-busy={busy === 'reset'}
                  onClick={() =>
                    run('reset', () => resetClientAccess(detail.organizationId), async (response) => {
                      onLink(detail.name, parseClientInvitation(await response.json()), 'RESET')
                    })
                  }
                >
                  {busy === 'reset' ? 'Gerando...' : 'Redefinir acesso'}
                </button>
              )}
              {detail.active && !detail.hasUser && (
                <button
                  type="button"
                  className={PRIMARY_BUTTON}
                  disabled={busy !== null}
                  aria-busy={busy === 'invite'}
                  onClick={() =>
                    run('invite', () => reinviteClient(detail.organizationId), async (response) => {
                      onLink(detail.name, parseClientInvitation(await response.json()), 'INVITE')
                    })
                  }
                >
                  {busy === 'invite' ? 'Gerando...' : 'Novo convite'}
                </button>
              )}
              {detail.active && !confirmingDeactivate && (
                <button type="button" className={SECONDARY_BUTTON} disabled={busy !== null} onClick={() => setConfirmingDeactivate(true)}>
                  Desativar cliente
                </button>
              )}
              {!detail.active && (
                <button
                  type="button"
                  className={PRIMARY_BUTTON}
                  disabled={busy !== null}
                  aria-busy={busy === 'reactivate'}
                  onClick={() =>
                    run('reactivate', () => setClientActive(detail.organizationId, true), async () => {
                      setNotice(null)
                    })
                  }
                >
                  {busy === 'reactivate' ? 'Reativando...' : 'Reativar cliente'}
                </button>
              )}
            </div>
            {confirmingDeactivate && (
              <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--color-border)] px-3 py-3">
                <p className="text-sm text-[var(--color-text-primary)]">
                  Desativar encerra o acesso do cliente e para a coleta da usina. Nada é apagado; dá para reativar
                  depois. Confirma?
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className={PRIMARY_BUTTON}
                    disabled={busy !== null}
                    aria-busy={busy === 'deactivate'}
                    onClick={() =>
                      run('deactivate', () => setClientActive(detail.organizationId, false), async () => {
                        setConfirmingDeactivate(false)
                      })
                    }
                  >
                    {busy === 'deactivate' ? 'Desativando...' : 'Sim, desativar'}
                  </button>
                  <button type="button" className={SECONDARY_BUTTON} disabled={busy !== null} onClick={() => setConfirmingDeactivate(false)}>
                    Cancelar
                  </button>
                </div>
              </div>
            )}
            <p className="text-xs leading-5 text-[var(--color-text-secondary)]">
              {detail.hasUser
                ? '“Redefinir acesso” gera um link de uso único: o cliente cria uma senha nova e as sessões antigas dele são encerradas.'
                : 'O cliente ainda não criou a senha. “Novo convite” gera outro link e o anterior deixa de valer.'}
            </p>
          </div>
        </Card>
      </section>

      <section aria-labelledby="client-activity-heading">
        <h3 id="client-activity-heading" className="mb-3 text-base font-semibold text-[var(--color-text-primary)]">
          Histórico
        </h3>
        <Card className="sm:p-6">
          {detail.activity.length === 0 ? (
            <p className="text-sm text-[var(--color-text-secondary)]">Nenhuma atividade registrada ainda.</p>
          ) : (
            <ol className="space-y-3" aria-label="Histórico do cliente">
              {detail.activity.map((item, index) => (
                <li key={`${item.at}-${index}`} className="flex gap-3">
                  <span
                    aria-hidden="true"
                    className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                      item.outcome === 'FAILED' ? 'bg-[var(--color-warning)]' : 'bg-[var(--color-success)]'
                    }`}
                  />
                  <div className="min-w-0">
                    <p className="text-sm text-[var(--color-text-primary)]">
                      {describeActivity(item)}
                      {item.outcome === 'FAILED' && <span className="sr-only"> (falhou)</span>}
                    </p>
                    <p className="text-xs text-[var(--color-text-secondary)]">{formatMoment(item.at)}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </section>
    </div>
  )
}
