import { useEffect } from 'react'
import { Link } from 'react-router'
import { fetchMonthlyProductionHistory } from '../lib/api'
import { parseCycleLedger, type CycleLedger, type LedgerCycle } from '../lib/dashboard/cycle-ledger-contracts'
import {
  LEDGER_BILL_NOTE,
  LEDGER_COMMISSIONING_UNKNOWN_NOTE,
  LEDGER_COMMISSIONING_UNKNOWN_NO_TOTAL_NOTE,
  LEDGER_NEGATIVE_NOTE,
  LEDGER_SEAL_ESTIMATED,
  LEDGER_SNAPSHOT_NOTE,
  formatCalculatedOn,
  formatLedgerMoney,
  isNegativeMoney,
  ledgerExclusionText,
  ledgerExtraSeals,
  ledgerLeftOutNote,
  ledgerQualityNote,
  ledgerReasonText,
  ledgerTotalLine,
} from '../lib/dashboard/cycle-ledger-text'
import { formatCycleLabel } from '../lib/format'
import { usePlantResource } from '../hooks/usePlantResource'
import { DASHBOARD_SETUP_PATH } from '../routes'
import { EmptyState } from './EmptyState'
import { LoadingAnnouncement } from './LoadingAnnouncement'
import { RetryableError } from './RetryableError'
import { SectionTitle } from './SectionTitle'

// "A conta, ciclo a ciclo": fatura e economia estimada dos últimos ciclos
// fechados, lidas do relatório gravado de cada ciclo (`/reports/monthly/history`).
// Sem conta no frontend: o total vem pronto de `savings_window`. Ciclo sem
// economia mostra o motivo em palavras, nunca R$ 0,00.

const HISTORY_LIMIT = 12
const NOTE_CLASS = 'text-[13px] leading-5 text-[var(--color-text-secondary)]'
const SEAL_CLASS =
  'inline-block rounded border border-[var(--color-border)] px-1.5 py-0.5 text-xs font-semibold text-[var(--color-text-secondary)]'

function SavingsCell({ cycle }: { cycle: LedgerCycle }) {
  const exclusion = ledgerExclusionText(cycle)
  const calculatedOn = formatCalculatedOn(cycle.reportCreatedAt)
  return (
    <td className="py-2.5 pl-2 align-top">
      {cycle.estimatedSavingsBrl !== null ? (
        <>
          <span className="font-semibold">{formatLedgerMoney(cycle.estimatedSavingsBrl)}</span>{' '}
          <span className="text-xs font-semibold text-[var(--color-chart-reference)]">{LEDGER_SEAL_ESTIMATED}</span>
          {isNegativeMoney(cycle.estimatedSavingsBrl) && <p className={`mt-1 ${NOTE_CLASS}`}>{LEDGER_NEGATIVE_NOTE}</p>}
          {ledgerExtraSeals(cycle).map((seal) => (
            <p key={seal} className="mt-1">
              <span className={SEAL_CLASS}>{seal}</span>
            </p>
          ))}
        </>
      ) : (
        <p className={NOTE_CLASS}>{ledgerReasonText(cycle.savingsUnavailableReason)}</p>
      )}
      {exclusion && <p className={`mt-1 font-medium ${NOTE_CLASS}`}>{exclusion}</p>}
      {calculatedOn && <p className={`mt-1 ${NOTE_CLASS}`}>Calculado em {calculatedOn}</p>}
    </td>
  )
}

function LedgerContent({ ledger }: { ledger: CycleLedger }) {
  const { window } = ledger
  const leftOut = window ? ledgerLeftOutNote(window) : null
  const quality = window && window.totalEstimatedSavingsBrl !== null ? ledgerQualityNote(window) : null
  return (
    <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-[var(--shadow-card)] sm:p-5">
      <p className={NOTE_CLASS}>{LEDGER_BILL_NOTE}</p>
      <table className="mt-3 w-full text-left text-sm tabular-nums">
        <caption className="sr-only">
          Valor da fatura e economia estimada de cada ciclo fechado, do mais recente ao mais antigo, em reais
        </caption>
        <thead className="text-[13px] text-[var(--color-text-secondary)]">
          <tr>
            <th scope="col" className="py-1.5 pr-2 font-medium">Ciclo</th>
            <th scope="col" className="py-1.5 px-2 font-medium">Valor da fatura</th>
            <th scope="col" className="py-1.5 pl-2 font-medium">Economia estimada</th>
          </tr>
        </thead>
        <tbody className="text-[var(--color-text-primary)]">
          {ledger.cycles.map((cycle) => (
            <tr key={`${cycle.billId}-${cycle.reportCreatedAt ?? ''}`} className="border-t border-[var(--color-border)]">
              <th scope="row" className="py-2.5 pr-2 align-top font-semibold">
                {formatCycleLabel(cycle.referenceMonth)}
              </th>
              <td className="px-2 py-2.5 align-top">
                {cycle.billTotalAmountBrl !== null ? (
                  formatLedgerMoney(cycle.billTotalAmountBrl)
                ) : (
                  <span className={NOTE_CLASS}>Valor indisponível</span>
                )}
              </td>
              <SavingsCell cycle={cycle} />
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 border-t border-[var(--color-border)] pt-3">
        {window ? (
          <>
            <p className="text-sm font-semibold text-[var(--color-text-primary)]">
              {ledgerTotalLine(window)}
              {window.totalEstimatedSavingsBrl !== null && (
                <span className="ml-2 text-xs font-semibold text-[var(--color-chart-reference)]">
                  {LEDGER_SEAL_ESTIMATED}
                </span>
              )}
            </p>
            {leftOut && <p className={`mt-1 ${NOTE_CLASS}`}>{leftOut}</p>}
            {quality && <p className={`mt-1 ${NOTE_CLASS}`}>{quality}</p>}
            {!window.commissioningKnown && (
              <p className={`mt-1 ${NOTE_CLASS}`}>
                {window.totalEstimatedSavingsBrl === null
                  ? LEDGER_COMMISSIONING_UNKNOWN_NO_TOTAL_NOTE
                  : LEDGER_COMMISSIONING_UNKNOWN_NOTE}{' '}
                <Link to={DASHBOARD_SETUP_PATH} className="font-semibold text-[var(--color-brand-primary)] underline">
                  Minha usina
                </Link>
                .
              </p>
            )}
          </>
        ) : (
          <p className={NOTE_CLASS}>Soma indisponível: esta versão do servidor ainda não informa o total.</p>
        )}
        <p className={`mt-1 ${NOTE_CLASS}`}>{LEDGER_SNAPSHOT_NOTE}</p>
      </div>
    </div>
  )
}

export function CycleLedgerSection({ plantId, refreshKey = 0 }: { plantId: string; refreshKey?: number }) {
  const resource = usePlantResource({
    plantId,
    fetcher: (id) => fetchMonthlyProductionHistory(id, HISTORY_LIMIT),
    parse: parseCycleLedger,
    errorMessage: 'Erro ao buscar a conta de cada ciclo.',
  })
  const { refetch } = resource
  useEffect(() => {
    if (refreshKey > 0) refetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])
  const loading = resource.data === null && !resource.error
  return (
    <section aria-labelledby="cycle-ledger-heading">
      <SectionTitle as="h2" id="cycle-ledger-heading">
        A conta, ciclo a ciclo
      </SectionTitle>
      <p className="-mt-1 mb-3 text-[13px] text-[var(--color-text-secondary)]">
        Até os últimos 12 ciclos fechados, em R$
      </p>
      <LoadingAnnouncement active={loading} message="Carregando a conta de cada ciclo." />
      {resource.error ? (
        <RetryableError message={resource.error} onRetry={resource.refetch} />
      ) : resource.data === null ? (
        <div
          className="h-40 animate-pulse rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)]"
          aria-hidden="true"
        />
      ) : resource.data.cycles.length === 0 ? (
        <EmptyState
          title="Nenhum ciclo com relatório ainda"
          description="Quando uma fatura for confirmada e o relatório do ciclo for gerado, a conta aparece aqui."
          action={
            <a
              href="#faturas"
              className="inline-flex min-h-[44px] items-center text-sm font-semibold text-[var(--color-brand-primary)] underline underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
            >
              Importar uma fatura
            </a>
          }
        />
      ) : (
        <LedgerContent ledger={resource.data} />
      )}
    </section>
  )
}
