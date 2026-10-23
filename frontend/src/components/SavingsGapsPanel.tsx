import { useEffect, useRef, useState } from 'react'
import { fetchSavingsGaps, reprocessSavingsGaps } from '../lib/api'
import {
  parseReprocessResults,
  parseSavingsGaps,
  type ReprocessResult,
  type SavingsGap,
} from '../lib/dashboard/savings-gaps-contracts'
import { formatCurrency } from '../lib/format'
import { usePlantResource } from '../hooks/usePlantResource'
import { LoadingAnnouncement } from './LoadingAnnouncement'

// "Meses a recalcular" (ADR-081). Faturas já confirmadas cuja economia ficou
// fora da soma do retorno do investimento, ou foi calculada pela fórmula
// antiga (tarifa SCEE, ADR-080). Recalcular grava uma NOVA versão do relatório
// mensal; a anterior fica guardada para auditoria. Todo número vem do backend.
// Sem meses a recalcular, o painel não aparece.

const SECONDARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-semibold text-[var(--color-text-primary)] transition-colors duration-200 hover:bg-[var(--color-surface-subtle)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

const MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

function month(referenceMonth: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(referenceMonth)
  const name = match ? MONTHS[Number(match[2]) - 1] : undefined
  return match && name ? `${name}/${match[1]}` : referenceMonth
}

function unavailableReason(reason: string | null): string {
  switch (reason) {
    case 'NO_PRODUCTION_DATA':
      return 'sem produção do inversor registrada no período'
    case 'TARIFF_NOT_AVAILABLE':
      return 'a fatura não trouxe a tarifa'
    case 'NO_CONSUMPTION_DATA':
      return 'sem dado de consumo no período'
    default:
      return 'economia indisponível'
  }
}

function gapText(gap: SavingsGap): string {
  switch (gap.cause) {
    case 'REPORT_MISSING':
      return 'Fatura confirmada antes de existir o relatório mensal.'
    case 'REPORT_PREDATES_SAVINGS':
      return 'Relatório anterior ao cálculo de economia.'
    case 'SAVINGS_UNAVAILABLE':
      return `Economia indisponível: ${unavailableReason(gap.savingsUnavailableReason)}.`
    case 'OUTDATED_CALCULATION':
      return gap.previousSavingsBrl == null
        ? 'Economia calculada pela fórmula antiga: pode estar subestimada.'
        : `Economia de ${formatCurrency(gap.previousSavingsBrl)} calculada pela fórmula antiga: pode estar subestimada.`
  }
}

function resultText(result: ReprocessResult): string {
  if (result.outcome === 'STILL_UNAVAILABLE') {
    return `continua indisponível (${unavailableReason(result.savingsUnavailableReason)}).`
  }
  if (result.storedRevision == null) return 'nada mudou com os dados atuais.'
  const now = formatCurrency(result.estimatedSavingsBrl)
  return result.previousSavingsBrl == null
    ? `economia de ${now}.`
    : `economia passou de ${formatCurrency(result.previousSavingsBrl)} para ${now}.`
}

export function SavingsGapsPanel({
  plantId,
  onReprocessed,
  reloadToken = 0,
}: {
  plantId: string
  onReprocessed: () => void
  // Muda quando uma fatura é confirmada ou completada: a lista é relida.
  reloadToken?: number
}) {
  const gaps = usePlantResource({
    plantId,
    fetcher: fetchSavingsGaps,
    parse: parseSavingsGaps,
    errorMessage: 'Erro ao buscar meses a recalcular.',
  })
  const refetchGaps = useRef(gaps.refetch)
  refetchGaps.current = gaps.refetch
  const firstToken = useRef(reloadToken)
  useEffect(() => {
    if (reloadToken !== firstToken.current) refetchGaps.current()
  }, [reloadToken])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<ReprocessResult[] | null>(null)

  async function reprocess() {
    setBusy(true)
    setError(null)
    try {
      const response = await reprocessSavingsGaps(plantId)
      if (!response.ok) {
        setError(
          response.status === 403
            ? 'Seu perfil não tem permissão para recalcular.'
            : 'Não foi possível recalcular agora. Tente novamente.',
        )
        return
      }
      setResults(parseReprocessResults(await response.json()))
      gaps.refetch()
      onReprocessed()
    } catch {
      setError('Não foi possível recalcular agora. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  const items = gaps.data ?? []
  if (items.length === 0 && results === null) return null

  return (
    <section
      aria-labelledby="savings-gaps-heading"
      className="mt-5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4"
    >
      <h3 id="savings-gaps-heading" className="text-[15px] font-semibold text-[var(--color-text-primary)]">
        Meses a recalcular
      </h3>
      <p className="mt-1 text-[13px] leading-5 text-[var(--color-text-secondary)]">
        Estas faturas já foram confirmadas, mas a economia delas ficou fora do retorno do investimento ou foi
        calculada pela fórmula antiga. Recalcular cria uma nova versão do relatório; a anterior fica guardada.
      </p>
      {items.length > 0 && (
        <ul className="mt-3 space-y-1.5 text-[13px] leading-5">
          {items.map((gap) => (
            <li key={gap.billId}>
              <span className="font-semibold text-[var(--color-text-primary)]">{month(gap.referenceMonth)}:</span>{' '}
              <span className="text-[var(--color-text-secondary)]">{gapText(gap)}</span>
            </li>
          ))}
        </ul>
      )}
      {items.length > 0 && (
        <button type="button" className={`${SECONDARY_BUTTON} mt-3`} disabled={busy} aria-busy={busy} onClick={reprocess}>
          {busy ? 'Recalculando...' : items.length === 1 ? 'Recalcular 1 mês' : `Recalcular ${items.length} meses`}
        </button>
      )}
      <LoadingAnnouncement active={busy} message="Recalculando os meses, aguarde." />
      {error && (
        <p role="alert" className="mt-3 text-sm text-[var(--color-danger-text)]">
          {error}
        </p>
      )}
      {results && (
        <div role="status" className="mt-3 text-[13px] leading-5">
          <p className="font-semibold text-[var(--color-text-primary)]">Resultado do recálculo</p>
          <ul className="mt-1 space-y-1">
            {results.map((result) => (
              <li key={result.billId} className="text-[var(--color-text-secondary)]">
                <span className="font-semibold text-[var(--color-text-primary)]">{month(result.referenceMonth)}:</span>{' '}
                {resultText(result)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
