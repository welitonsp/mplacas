import { FormEvent, useCallback, useEffect, useId, useRef, useState } from 'react'
import { Card } from '../../components/Card'
import { INPUT_CLASS, PRIMARY_BUTTON, SECONDARY_BUTTON } from '../../components/BrandLoginForm'
import { LoadingAnnouncement } from '../../components/LoadingAnnouncement'
import { PageHeader } from '../../components/PageHeader'
import { RetryableError } from '../../components/RetryableError'
import { SectionTitle } from '../../components/SectionTitle'
import { useMe } from '../../contexts/MeContext'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import { createClient, fetchClients, reinviteClient } from '../../lib/api'
import {
  buildInvitationLink,
  clientErrorMessage,
  parseClientInvitation,
  parseClients,
  type ClientInvitation,
  type ClientSummary,
} from '../../lib/dashboard/onboarding-contracts'

// "Clientes" do dono da plataforma (ADR-093). Convidar = criar o cliente e
// gerar um link de uso único (`/convite#token=...`), que o dono copia e manda
// só ao cliente. O link aparece uma vez, fica só na memória desta tela e não
// pode ser recuperado depois — para reenviar, gera-se outro (o anterior deixa
// de valer).

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function clientStatus(client: ClientSummary): string {
  if (!client.active) return 'Desativado'
  if (client.connections > 0) return 'Usina conectada'
  if (client.users > 0) return 'Entrou, falta conectar a usina'
  if (client.invitationPendingUntil) return `Convite enviado (vale até ${formatDate(client.invitationPendingUntil)})`
  return 'Convite vencido'
}

function InvitationLink({
  name,
  invitation,
  onClose,
}: {
  name: string
  invitation: ClientInvitation
  onClose: () => void
}) {
  const link = buildInvitationLink(window.location.origin, invitation.token)
  const [copied, setCopied] = useState<'ok' | 'fail' | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const linkId = useId()

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  async function copy() {
    try {
      await navigator.clipboard.writeText(link)
      setCopied('ok')
    } catch {
      setCopied('fail')
    }
  }

  return (
    <Card className="border-[var(--color-brand-primary)] sm:p-6">
      <div className="space-y-4">
        <h2 ref={headingRef} tabIndex={-1} className="text-base font-semibold text-[var(--color-text-primary)] focus:outline-none">
          Link do convite de {name}
        </h2>
        <p className="text-sm leading-6 text-[var(--color-text-secondary)]">
          Mande este link <strong>só para {invitation.username}</strong> (WhatsApp ou e-mail). Quem abrir primeiro cria a
          senha. Ele vale até {formatDate(invitation.expiresAt)} e não aparece de novo depois que você fechar este aviso.
        </p>
        <label htmlFor={linkId} className="sr-only">
          Link do convite
        </label>
        <input
          id={linkId}
          readOnly
          value={link}
          onFocus={(event) => event.currentTarget.select()}
          className={`${INPUT_CLASS} font-mono text-xs`}
        />
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={PRIMARY_BUTTON} onClick={copy}>
            Copiar link
          </button>
          <button type="button" className={SECONDARY_BUTTON} onClick={onClose}>
            Já enviei, fechar
          </button>
          <span role="status" className="text-sm text-[var(--color-text-secondary)]">
            {copied === 'ok' ? 'Link copiado.' : copied === 'fail' ? 'Não deu para copiar: selecione o link e copie.' : ''}
          </span>
        </div>
      </div>
    </Card>
  )
}

function NewClientForm({ onCreated }: { onCreated: (name: string, invitation: ClientInvitation) => void }) {
  const nameId = useId()
  const emailId = useId()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (!name.trim()) {
      setError('Informe o nome do cliente.')
      return
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError('Informe um e-mail válido para o cliente.')
      return
    }
    setSaving(true)
    try {
      const response = await createClient({ name: name.trim(), admin_username: email.trim() })
      if (!response.ok) {
        setError(await clientErrorMessage(response))
        return
      }
      const invitation = parseClientInvitation(await response.json())
      const created = name.trim()
      setName('')
      setEmail('')
      onCreated(created, invitation)
    } catch {
      setError('Não foi possível concluir agora. Tente novamente.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4" aria-label="Convidar cliente">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor={nameId} className="mb-1 block text-[13px] font-semibold text-[var(--color-text-primary)]">
            Nome do cliente
          </label>
          <input
            id={nameId}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={saving}
            placeholder="Ex.: Rogério Silva"
            maxLength={120}
            className={INPUT_CLASS}
          />
        </div>
        <div>
          <label htmlFor={emailId} className="mb-1 block text-[13px] font-semibold text-[var(--color-text-primary)]">
            E-mail do cliente (vira o usuário dele)
          </label>
          <input
            id={emailId}
            type="email"
            autoCapitalize="none"
            spellCheck={false}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={saving}
            maxLength={80}
            className={INPUT_CLASS}
          />
        </div>
      </div>
      {error && (
        <div role="alert" className="rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] px-3 py-2 text-sm text-[var(--color-danger-text)]">
          {error}
        </div>
      )}
      <button type="submit" className={PRIMARY_BUTTON} disabled={saving} aria-busy={saving}>
        {saving ? 'Gerando convite...' : 'Gerar convite'}
      </button>
      <LoadingAnnouncement active={saving} message="Gerando o convite, aguarde." />
    </form>
  )
}

export function ClientsPage() {
  const headingRef = useModuleTitle('Clientes')
  const { me, loading: meLoading } = useMe()
  const [clients, setClients] = useState<ClientSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [shown, setShown] = useState<{ name: string; invitation: ClientInvitation } | null>(null)
  const [reinviting, setReinviting] = useState<string | null>(null)
  const [rowError, setRowError] = useState<string | null>(null)
  // Ao fechar o aviso do link, o foco volta para o formulário (WCAG 2.4.3).
  const formAreaRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const response = await fetchClients()
      if (!response.ok) {
        setError(await clientErrorMessage(response))
        return
      }
      setClients(parseClients(await response.json()))
    } catch {
      setError('Erro ao buscar os clientes.')
    }
  }, [])

  useEffect(() => {
    if (me?.isPlatformOperator) void load()
  }, [me, load])

  async function handleReinvite(client: ClientSummary) {
    setRowError(null)
    setReinviting(client.organizationId)
    try {
      const response = await reinviteClient(client.organizationId)
      if (!response.ok) {
        setRowError(await clientErrorMessage(response))
        return
      }
      setShown({ name: client.name, invitation: parseClientInvitation(await response.json()) })
      void load()
    } catch {
      setRowError('Não foi possível gerar o novo convite agora.')
    } finally {
      setReinviting(null)
    }
  }

  if (meLoading) {
    return (
      <>
        <PageHeader eyebrow="Plataforma" title="Clientes" description="Carregando..." headingRef={headingRef} />
        <p role="status" className="text-sm text-[var(--color-text-secondary)]">
          Carregando...
        </p>
      </>
    )
  }

  if (!me?.isPlatformOperator) {
    return (
      <>
        <PageHeader eyebrow="Plataforma" title="Clientes" description="Área do dono da plataforma." headingRef={headingRef} />
        <Card>
          <p className="text-sm text-[var(--color-text-secondary)]">Esta área é só para o dono da plataforma.</p>
        </Card>
      </>
    )
  }

  return (
    <>
      <PageHeader
        eyebrow="Plataforma"
        title="Clientes"
        description="Convide donos de usina para usar o MPlacas e acompanhe quem já conectou a usina."
        headingRef={headingRef}
      />
      <div className="space-y-6">
        {shown && (
          <InvitationLink
            name={shown.name}
            invitation={shown.invitation}
            onClose={() => {
              setShown(null)
              requestAnimationFrame(() => formAreaRef.current?.focus())
            }}
          />
        )}

        <section aria-labelledby="new-client-heading">
          <SectionTitle as="h2" id="new-client-heading">
            Convidar cliente
          </SectionTitle>
          <div ref={formAreaRef} tabIndex={-1} className="rounded-[var(--radius-card)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]">
          <Card className="sm:p-6">
            <NewClientForm
              onCreated={(name, invitation) => {
                setShown({ name, invitation })
                void load()
              }}
            />
          </Card>
          </div>
        </section>

        <section aria-labelledby="clients-heading">
          <SectionTitle as="h2" id="clients-heading">
            Seus clientes
          </SectionTitle>
          <Card className="sm:p-6">
            {error && <RetryableError message={error} onRetry={() => void load()} />}
            {rowError && (
              <div role="alert" className="mb-3 rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] px-3 py-2 text-sm text-[var(--color-danger-text)]">
                {rowError}
              </div>
            )}
            {!clients && !error && (
              <p role="status" className="text-sm text-[var(--color-text-secondary)]">
                Buscando clientes...
              </p>
            )}
            {clients && clients.length === 0 && (
              <p className="text-sm text-[var(--color-text-secondary)]">Nenhum cliente ainda. Convide o primeiro acima.</p>
            )}
            {clients && clients.length > 0 && (
              <ul className="divide-y divide-[var(--color-border)]" aria-label="Clientes">
                {clients.map((client) => {
                  const canReinvite = client.active && client.users === 0
                  return (
                    <li key={client.organizationId} className="flex flex-wrap items-center justify-between gap-3 py-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-[var(--color-text-primary)]">{client.name}</p>
                        <p className="text-[13px] text-[var(--color-text-secondary)]">
                          {client.adminUsername ?? 'sem e-mail'} · {clientStatus(client)}
                        </p>
                      </div>
                      {canReinvite && (
                        <button
                          type="button"
                          className={SECONDARY_BUTTON}
                          onClick={() => handleReinvite(client)}
                          disabled={reinviting !== null}
                          aria-busy={reinviting === client.organizationId}
                          aria-label={`Gerar novo convite para ${client.name}`}
                        >
                          {reinviting === client.organizationId ? 'Gerando...' : 'Novo convite'}
                        </button>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </Card>
        </section>
      </div>
    </>
  )
}
