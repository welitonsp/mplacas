import { useState } from 'react'
import { confirmBill } from '../lib/api'
import type { UtilityBill } from '../lib/dashboard/bill-contracts'
import { LoadingAnnouncement } from './LoadingAnnouncement'

// Confirmar várias faturas conferidas de uma vez (importação em lote).
// Dois cliques de propósito: o primeiro pergunta se os valores de TODAS foram
// conferidos; só o segundo confirma. Cada fatura passa pela mesma rota de
// confirmação individual (relatório mensal imutável + auditoria por fatura).

const PRIMARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--color-brand-primary)] px-4 py-2 text-sm font-semibold text-[var(--color-on-brand)] shadow-sm transition-colors duration-200 hover:bg-[var(--color-brand-primary-dark)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

const SECONDARY_BUTTON =
  'inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-semibold text-[var(--color-text-primary)] transition-colors duration-200 hover:bg-[var(--color-surface-subtle)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none'

export interface BulkConfirmResult {
  confirmed: number
  failed: string[] // meses que não foram confirmados
}

export function BulkConfirmBar({
  bills,
  label,
  onDone,
}: {
  bills: UtilityBill[]
  label: (bill: UtilityBill) => string
  onDone: (result: BulkConfirmResult) => void
}) {
  const [asking, setAsking] = useState(false)
  const [busy, setBusy] = useState<{ done: number; total: number } | null>(null)

  async function confirmAll() {
    setBusy({ done: 0, total: bills.length })
    let confirmed = 0
    const failed: string[] = []
    for (const [index, bill] of bills.entries()) {
      try {
        const response = await confirmBill(bill.id)
        if (response.ok) confirmed += 1
        else failed.push(label(bill))
      } catch {
        failed.push(label(bill))
      }
      setBusy({ done: index + 1, total: bills.length })
    }
    setBusy(null)
    setAsking(false)
    onDone({ confirmed, failed })
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
      {asking ? (
        <>
          <p className="text-sm text-[var(--color-text-primary)]">
            Você conferiu os valores das {bills.length} faturas abaixo com as faturas impressas? Depois de confirmadas,
            elas entram na economia e no retorno do investimento.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <button
              type="button"
              className={PRIMARY_BUTTON}
              disabled={busy !== null}
              aria-busy={busy !== null}
              onClick={confirmAll}
            >
              {busy ? `Confirmando ${busy.done + 1 > busy.total ? busy.total : busy.done + 1} de ${busy.total}...` : `Sim, confirmar ${bills.length} faturas`}
            </button>
            <button type="button" className={SECONDARY_BUTTON} disabled={busy !== null} onClick={() => setAsking(false)}>
              Cancelar
            </button>
          </div>
          <LoadingAnnouncement active={busy !== null} message="Confirmando as faturas, aguarde." />
        </>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-[var(--color-text-primary)]">
            {bills.length} faturas aguardando conferência.
          </p>
          <button type="button" className={SECONDARY_BUTTON} onClick={() => setAsking(true)}>
            Confirmar todas
          </button>
        </div>
      )}
    </div>
  )
}
