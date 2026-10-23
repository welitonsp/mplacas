import { ChangeEvent, useCallback, useRef, useState } from 'react'
import { confirmBill, fetchPendingBills, rejectBill, uploadBillPdf } from '../lib/api'
import {
  parseBillEnvelope,
  parsePendingBills,
  type UtilityBill,
} from '../lib/dashboard/bill-contracts'
import { formatCurrency, formatCycleLabel, formatFullDate, formatNumber } from '../lib/format'
import { usePlantResource } from '../hooks/usePlantResource'
import { Card } from './Card'
import { LoadingAnnouncement } from './LoadingAnnouncement'
import { RetryableError } from './RetryableError'
import { SectionTitle } from './SectionTitle'
import { SavingsGapsPanel } from './SavingsGapsPanel'
import { BulkConfirmBar } from './BulkConfirmBar'

// Importar e conferir faturas de energia pelo site (fase 2 do plano de
// inteligência financeira). Fluxo:
//   1. o dono da usina escolhe o PDF da fatura da Equatorial;
//   2. o backend lê o texto (mesmo leitor do Telegram) e cria a fatura como
//      PENDENTE — nada entra nas contas ainda;
//   3. a tela mostra o que foi lido, campo a campo, para conferência humana;
//   4. "Confirmar" materializa o relatório mensal imutável (ADR-038) e a
//      economia passa a contar no retorno do investimento (ADR-067).
// Faturas que chegaram pelo Telegram aparecem na mesma lista de pendentes.
//
// Perfil: importar/confirmar/rejeitar exigem ADMIN no backend. Uma credencial
// READ vê o card e recebe a mensagem de permissão ao tentar — mesma limitação
// conhecida do `CapexRegistrationForm` (o frontend ainda não distingue papel).

const MAX_PDF_BYTES = 10_000_000 // espelha `telegram_document_max_bytes` do backend

const PRIMARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--color-brand-primary)] px-4 py-2 text-sm font-semibold text-[var(--color-on-brand)] shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-[var(--color-brand-primary-dark)] hover:shadow-md active:translate-y-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 motion-reduce:transition-none'

const SECONDARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-semibold text-[var(--color-text-primary)] transition-colors duration-200 hover:bg-[var(--color-surface-subtle)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

const DANGER_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--color-danger-text)] px-4 py-2 text-sm font-semibold text-[var(--color-surface)] transition-colors duration-200 hover:bg-[var(--color-danger)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-danger)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

type Feedback = { tone: 'success' | 'info' | 'error'; message: string }
// Resultado da leitura de um arquivo; `billId` quando ficou uma pendência.
type ImportOutcome = Feedback & { month?: string; billId?: string; completed?: boolean }
type BatchItem = ImportOutcome & { fileName: string }

// Um ano e meio de contas por vez: cobre "mandar o ano inteiro" com folga e
// mantém a leitura sequencial (PDF isolado no servidor) num tempo razoável.
const MAX_BATCH_FILES = 18

const FEEDBACK_CLASS: Record<Feedback['tone'], string> = {
  success:
    'border-[var(--color-success)]/30 bg-[var(--color-success-light)] text-[var(--color-success-text)]',
  info: 'border-[var(--color-border)] bg-[var(--color-surface-subtle)] text-[var(--color-text-primary)]',
  error:
    'border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] text-[var(--color-danger-text)]',
}

function kwh(value: string | null): string {
  return value == null ? 'Não informado na fatura' : `${formatNumber(value, 2)} kWh`
}

// Tarifas com 6 casas fixas, exatamente como a fatura imprime (0,613030 e não
// 0,61303) — a conferência é comparar dígito a dígito com o papel.
function tariff(value: string | null): string {
  if (value == null) return 'Não informada na fatura'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return value
  return `R$ ${numeric.toLocaleString('pt-BR', { minimumFractionDigits: 6, maximumFractionDigits: 6 })}/kWh`
}

// "set/2026", como o campo REF: MÊS/ANO da fatura.
function monthLabel(bill: UtilityBill): string {
  const short = formatCycleLabel(bill.referenceMonth)
  const year = bill.referenceMonth.slice(0, 4)
  return short.includes('/') ? `${short.split('/')[0]}/${year}` : short
}

async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json()
    if (typeof body === 'object' && body !== null && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      return typeof detail === 'string' ? detail : null
    }
  } catch {
    // corpo não-JSON: cai na mensagem genérica
  }
  return null
}

async function uploadErrorMessage(response: Response): Promise<string> {
  switch (response.status) {
    case 403:
      return 'Seu perfil não tem permissão para importar faturas.'
    case 404:
      return 'Usina não encontrada.'
    case 413:
      return 'O arquivo passa de 10 MB. Envie o PDF original da fatura.'
    case 409:
      // Textos fixos do backend (mês já confirmado com valores diferentes, ou
      // valores que não passaram na validação), sem trecho do documento.
      return (await readErrorDetail(response)) ?? 'Esta fatura conflita com outra já registrada.'
    case 415:
      return 'O arquivo enviado não é um PDF.'
    case 422:
      // As mensagens 422 do backend são textos fixos em português, sem trecho
      // do documento (ver `billing/router.py::intake_bill_pdf`).
      return (
        (await readErrorDetail(response)) ??
        'Não foi possível ler esta fatura. Envie o PDF original da Equatorial, sem senha.'
      )
    default:
      return 'Não foi possível importar a fatura agora. Tente novamente.'
  }
}

function BillField({ label, value, emphasis = false }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[13px] font-medium leading-5 text-[var(--color-text-secondary)]">{label}</dt>
      <dd
        className={
          emphasis
            ? 'mt-0.5 font-display text-[20px] font-semibold tabular-nums text-[var(--color-text-primary)]'
            : 'mt-0.5 text-[15px] font-semibold tabular-nums text-[var(--color-text-primary)]'
        }
      >
        {value}
      </dd>
    </div>
  )
}

function PendingBillReview({
  bill,
  highlighted,
  onConfirmed,
  onRejected,
}: {
  bill: UtilityBill
  highlighted: boolean
  onConfirmed: (bill: UtilityBill) => void
  onRejected: (bill: UtilityBill) => void
}) {
  const [busy, setBusy] = useState<'confirm' | 'reject' | null>(null)
  const [askingReject, setAskingReject] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const headingId = `bill-${bill.id}-heading`

  async function run(action: 'confirm' | 'reject') {
    setError(null)
    setBusy(action)
    try {
      const response = action === 'confirm' ? await confirmBill(bill.id) : await rejectBill(bill.id)
      if (!response.ok) {
        if (response.status === 403) {
          setError('Seu perfil não tem permissão para confirmar ou rejeitar faturas.')
        } else if (response.status === 409) {
          setError('Esta fatura já foi revisada. Atualize a página para ver o estado atual.')
        } else {
          setError('Não foi possível concluir agora. Tente novamente.')
        }
        return
      }
      const updated = parseBillEnvelope(await response.json())
      if (action === 'confirm') onConfirmed(updated)
      else onRejected(updated)
    } catch {
      setError('Não foi possível concluir agora. Tente novamente.')
    } finally {
      setBusy(null)
    }
  }

  // Na fatura SCEE da Equatorial, a linha "INJEÇÃO SCEE" (`injected_kwh`) é a
  // energia COMPENSADA no ciclo; a energia que de fato saiu para a rede é o
  // registro "ENERGIA GERAÇÃO" do medidor (`generation_cycle_kwh`). Conferido
  // na fatura real de set/2026: INJEÇÃO SCEE 221 kWh = consumo 221 kWh;
  // ENERGIA GERAÇÃO 235 kWh; 235 − 221 = 14 kWh de "excedente recebido" que
  // virou crédito (ver o documento de diagnóstico, seção "Primeira fatura
  // conferida"). Sem o registro do medidor, a tela NÃO afirma o que saiu para
  // a rede: mostra a linha da fatura com o nome que ela tem.
  const injectedField = bill.generationCycleKwh
    ? { label: 'Energia injetada na rede', value: kwh(bill.generationCycleKwh) }
    : { label: 'Injeção SCEE (como na fatura)', value: kwh(bill.injectedKwh) }

  return (
    <article
      aria-labelledby={headingId}
      className={`rounded-[var(--radius-card)] border p-4 sm:p-5 ${
        highlighted
          ? 'border-[var(--color-brand-primary)] bg-[var(--color-brand-primary-light)]/40'
          : 'border-[var(--color-border)] bg-[var(--color-surface)]'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={headingId} className="text-base font-semibold text-[var(--color-text-primary)]">
          Fatura de {monthLabel(bill)}
        </h3>
        <span className="inline-flex rounded-md bg-[var(--color-warning-light)] px-2 py-0.5 text-xs font-semibold text-[var(--color-warning-text)]">
          Aguardando sua conferência
        </span>
      </div>
      <p className="mt-1 text-[13px] leading-5 text-[var(--color-text-secondary)]">
        Compare com a fatura impressa. Só depois de confirmada ela entra na economia e no retorno do investimento.
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-[var(--color-border)] pt-4 lg:grid-cols-4">
        <BillField label="Total da fatura" value={formatCurrency(bill.totalAmountBrl)} emphasis />
        <BillField
          label="Ciclo"
          value={`${formatFullDate(bill.cycleStart)} a ${formatFullDate(bill.cycleEnd)} · ${bill.billedDays} dias`}
        />
        <BillField label="Energia puxada da rede" value={kwh(bill.importedKwh)} />
        <BillField label={injectedField.label} value={injectedField.value} />
        <BillField label="Energia compensada" value={kwh(bill.compensatedKwh)} />
        <BillField label="Saldo de créditos" value={kwh(bill.creditBalanceKwh)} />
        <BillField label="Iluminação pública" value={formatCurrency(bill.publicLightingBrl)} />
        <BillField label="Tarifa com impostos" value={tariff(bill.tariffWithTaxesBrlKwh)} />
        <BillField label="Tarifa sem impostos" value={tariff(bill.tariffWithoutTaxesBrlKwh)} />
        <BillField label="Tarifa do Fio B" value={tariff(bill.wireBTariffBrlKwh)} />
      </dl>

      {error && (
        <div role="alert" className={`mt-4 rounded-lg border px-3 py-2 text-sm ${FEEDBACK_CLASS.error}`}>
          {error}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {askingReject ? (
          <>
            <p className="w-full text-sm text-[var(--color-text-primary)]">
              Rejeitar esta fatura? Ela não entra nas contas, e você pode importá-la de novo depois.
            </p>
            <button
              type="button"
              className={DANGER_BUTTON}
              disabled={busy !== null}
              aria-busy={busy === 'reject'}
              onClick={() => run('reject')}
            >
              {busy === 'reject' ? 'Rejeitando...' : 'Sim, rejeitar'}
            </button>
            <button
              type="button"
              className={SECONDARY_BUTTON}
              disabled={busy !== null}
              onClick={() => setAskingReject(false)}
            >
              Cancelar
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className={PRIMARY_BUTTON}
              disabled={busy !== null}
              aria-busy={busy === 'confirm'}
              onClick={() => run('confirm')}
            >
              {busy === 'confirm' ? 'Confirmando...' : 'Confirmar fatura'}
            </button>
            <button
              type="button"
              className={SECONDARY_BUTTON}
              disabled={busy !== null}
              onClick={() => setAskingReject(true)}
            >
              Rejeitar
            </button>
          </>
        )}
      </div>
      <LoadingAnnouncement
        active={busy !== null}
        message={busy === 'confirm' ? 'Confirmando a fatura, aguarde.' : 'Rejeitando a fatura, aguarde.'}
      />
    </article>
  )
}

export function BillsSection({ plantId, onConfirmed }: { plantId: string; onConfirmed: () => void }) {
  const pending = usePlantResource({
    plantId,
    fetcher: fetchPendingBills,
    parse: parsePendingBills,
    errorMessage: 'Erro ao buscar faturas pendentes.',
  })
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const [gapsReload, setGapsReload] = useState(0)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const [batch, setBatch] = useState<BatchItem[] | null>(null)

  // Lê UM arquivo e devolve o que aconteceu, sem mexer na tela. Usado tanto
  // na importação de um arquivo quanto na importação em lote.
  const importOne = useCallback(
    async (file: File): Promise<ImportOutcome> => {
      if (file.size > MAX_PDF_BYTES) {
        return { tone: 'error', message: 'O arquivo passa de 10 MB. Envie o PDF original da fatura.' }
      }
      try {
        const response = await uploadBillPdf(plantId, file)
        if (!response.ok) return { tone: 'error', message: await uploadErrorMessage(response) }
        const payload: unknown = await response.json()
        const bill = parseBillEnvelope(payload)
        const outcome =
          typeof payload === 'object' && payload !== null && 'status' in payload
            ? (payload as { status: unknown }).status
            : null
        const month = monthLabel(bill)
        // PDF de um mês já confirmado que só completou campos vazios (ex.:
        // tarifa que o texto do Telegram não trazia) — ADR-081.
        if (outcome === 'completed_missing_fields') {
          return {
            tone: 'success',
            month,
            completed: true,
            message: `A fatura de ${month} já estava confirmada: completamos os dados que faltavam (como a tarifa). Use "Meses a recalcular" para atualizar a economia.`,
          }
        }
        // O backend é idempotente por conteúdo: a mesma fatura enviada de novo
        // devolve o registro que já existe, em qualquer estado.
        if (bill.status === 'CONFIRMED') {
          return { tone: 'info', month, message: `A fatura de ${month} já tinha sido importada e confirmada.` }
        }
        if (bill.status === 'REJECTED') {
          return { tone: 'info', month, message: `A fatura de ${month} já tinha sido importada e foi rejeitada.` }
        }
        // 200 = reenvio de uma fatura que já estava pendente; 202 = nova.
        return response.status === 200
          ? { tone: 'info', month, billId: bill.id, message: `A fatura de ${month} já tinha sido importada e aguarda sua conferência.` }
          : { tone: 'success', month, billId: bill.id, message: `Fatura de ${month} lida. Confira os valores abaixo e confirme.` }
      } catch {
        return { tone: 'error', message: 'Não foi possível importar a fatura agora. Tente novamente.' }
      }
    },
    [plantId],
  )

  const handleFile = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files ?? [])
      // Limpa o input para permitir escolher os mesmos arquivos de novo depois.
      event.target.value = ''
      if (files.length === 0) return
      setFeedback(null)
      setBatch(null)
      if (files.length > MAX_BATCH_FILES) {
        setFeedback({
          tone: 'error',
          message: `Escolha até ${MAX_BATCH_FILES} faturas por vez (um ano e meio de contas).`,
        })
        return
      }

      setUploading(true)
      setProgress({ done: 0, total: files.length })
      const results: BatchItem[] = []
      try {
        // Uma de cada vez: a leitura do PDF roda isolada e limitada no servidor.
        for (const [index, file] of files.entries()) {
          results.push({ fileName: file.name, ...(await importOne(file)) })
          setProgress({ done: index + 1, total: files.length })
        }
      } finally {
        setUploading(false)
        setProgress(null)
      }

      const last = [...results].reverse().find((item) => item.billId)
      if (last?.billId) setHighlightedId(last.billId)
      if (results.length === 1) {
        const [only] = results
        setFeedback({ tone: only.tone, message: only.message })
      } else {
        setBatch(results)
      }
      pending.refetch()
      if (results.some((item) => item.completed)) {
        setGapsReload((value) => value + 1)
        onConfirmed()
      }
    },
    [importOne, pending, onConfirmed],
  )

  const items = pending.data?.items ?? []

  return (
    <section aria-labelledby="bills-section-heading" className="mb-6">
      <SectionTitle as="h2" id="bills-section-heading">
        Faturas de energia
      </SectionTitle>
      <Card className="sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 max-w-2xl">
            <p className="text-[15px] font-semibold text-[var(--color-text-primary)]">
              Importe a fatura da Equatorial em PDF
            </p>
            <p className="mt-1 text-[13px] leading-5 text-[var(--color-text-secondary)]">
              O sistema lê a fatura e você confere cada valor antes de confirmar. Pode escolher várias de uma vez
              (por exemplo, o ano inteiro). O arquivo não fica guardado: só os valores lidos.
            </p>
          </div>
          <div>
            <input
              ref={inputRef}
              id="bill-pdf-input"
              type="file"
              multiple
              accept="application/pdf,.pdf"
              className="sr-only"
              tabIndex={-1}
              aria-hidden="true"
              onChange={handleFile}
            />
            <button
              type="button"
              className={PRIMARY_BUTTON}
              disabled={uploading}
              aria-busy={uploading}
              onClick={() => inputRef.current?.click()}
            >
              {uploading && (
                <span
                  aria-hidden="true"
                  className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current/40 border-t-current"
                />
              )}
              {uploading
                ? progress && progress.total > 1
                  ? `Lendo ${Math.min(progress.done + 1, progress.total)} de ${progress.total}...`
                  : 'Lendo a fatura...'
                : 'Importar faturas (PDF)'}
            </button>
          </div>
        </div>
        <LoadingAnnouncement active={uploading} message="Lendo as faturas, aguarde." />

        {feedback && (
          <div
            role={feedback.tone === 'error' ? 'alert' : 'status'}
            className={`mt-4 rounded-lg border px-3 py-2 text-sm ${FEEDBACK_CLASS[feedback.tone]}`}
          >
            {feedback.message}
          </div>
        )}

        {batch && (
          <div role="status" className="mt-4 rounded-lg border border-[var(--color-border)] px-3 py-3 text-sm">
            <p className="font-semibold text-[var(--color-text-primary)]">
              {batch.length} arquivos lidos: {batch.filter((item) => item.billId).length} para conferir
              {batch.some((item) => item.tone === 'error')
                ? `, ${batch.filter((item) => item.tone === 'error').length} com problema`
                : ''}
              .
            </p>
            <ul className="mt-2 space-y-1">
              {batch.map((item, index) => (
                <li
                  key={`${item.fileName}-${index}`}
                  className={
                    item.tone === 'error'
                      ? 'text-[var(--color-danger-text)]'
                      : 'text-[var(--color-text-secondary)]'
                  }
                >
                  <span className="font-medium">{item.fileName}:</span> {item.message}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-5 space-y-4">
          {pending.error ? (
            <RetryableError message={pending.error} onRetry={pending.refetch} />
          ) : pending.data === null ? (
            <div className="h-16 animate-pulse rounded-lg bg-[var(--color-surface-subtle)]" aria-hidden="true" />
          ) : items.length === 0 ? (
            <p className="text-[13px] text-[var(--color-text-secondary)]">Nenhuma fatura aguardando conferência.</p>
          ) : (
            <>
            {items.length > 1 && (
              <BulkConfirmBar
                bills={items}
                label={monthLabel}
                onDone={({ confirmed, failed }) => {
                  setBatch(null)
                  setFeedback(
                    failed.length === 0
                      ? {
                          tone: 'success',
                          message: `${confirmed} faturas confirmadas. Economia e retorno do investimento atualizados.`,
                        }
                      : {
                          tone: 'error',
                          message: `${confirmed} faturas confirmadas. Não foi possível confirmar: ${failed.join(', ')}. Tente essas de novo.`,
                        },
                  )
                  pending.refetch()
                  setGapsReload((value) => value + 1)
                  onConfirmed()
                }}
              />
            )}
            {items.map((bill) => (
              <PendingBillReview
                key={bill.id}
                bill={bill}
                highlighted={bill.id === highlightedId}
                onConfirmed={(updated) => {
                  setFeedback({
                    tone: 'success',
                    message: `Fatura de ${monthLabel(updated)} confirmada. Economia e retorno do investimento atualizados.`,
                  })
                  pending.refetch()
                  setGapsReload((value) => value + 1)
                  onConfirmed()
                }}
                onRejected={(updated) => {
                  setFeedback({ tone: 'info', message: `Fatura de ${monthLabel(updated)} rejeitada.` })
                  pending.refetch()
                }}
              />
            ))}
            </>
          )}
        </div>
        <SavingsGapsPanel plantId={plantId} reloadToken={gapsReload} onReprocessed={onConfirmed} />
      </Card>
    </section>
  )
}
