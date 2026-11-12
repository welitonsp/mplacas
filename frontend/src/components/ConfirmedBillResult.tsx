import { Link } from 'react-router'
import { fetchEnergyCycle, fetchMonthlyProductionHistory } from '../lib/api'
import { parseCycleSavings } from '../lib/dashboard/cycle-savings-contracts'
import { savingsUnavailableMessage } from '../lib/dashboard/contracts'
import { parseMonthlyProductionHistory } from '../lib/dashboard/monthly-history-contracts'
import { distributorDisplayName, verdictDetail } from '../lib/dashboard/utility-check-text'
import { formatCurrency } from '../lib/format'
import { usePlantResource } from '../hooks/usePlantResource'
import { DASHBOARD_PRODUCTION_PATH } from '../routes'

// Resposta no momento da confirmação: a jornada "a distribuidora me creditou
// direito?" terminava sem resposta, que só aparecia na aba Energia.
//
// De onde vem cada coisa (o relatório do ciclo é gravado de forma SÍNCRONA na
// própria confirmação — `billing/router.py::confirm_bill` chama
// `materialize_monthly_report_snapshot` antes de responder —, então não há job
// a esperar nem polling):
// - economia do ciclo: `GET /energy/cycles/{bill_id}` (a fatura confirmada);
// - veredito dos créditos: `GET /reports/monthly/history`, ciclo cujo `billId`
//   é o da fatura confirmada. O histórico só traz os ciclos mais recentes: um
//   ciclo fora da janela cai em "ainda não disponível", nunca num palpite.
// O texto do veredito é o MESMO da aba Energia (`verdictDetail`).

const UNAVAILABLE_CHECK =
  'A conferência deste ciclo ainda não está disponível. Ela aparece em Energia assim que for calculada.'

// Janela do histórico: o dobro do padrão da aba Energia, para cobrir quem
// confirma vários meses atrasados um a um.
const HISTORY_LIMIT = 24

const LINK_CLASS =
  'inline-flex min-h-[44px] items-center rounded-md text-sm font-semibold text-[var(--color-brand-primary)] underline underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2'

const PANEL_CLASS =
  'mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-3 py-3 text-sm text-[var(--color-text-primary)]'

export function ConfirmedBillResult({
  plantId,
  billId,
  cycleLabel,
}: {
  plantId: string
  billId: string
  cycleLabel: string
}) {
  const savings = usePlantResource({
    plantId,
    fetcher: (id) => fetchEnergyCycle(id, billId),
    parse: parseCycleSavings,
    errorMessage: 'Erro ao buscar a economia do ciclo.',
  })
  const history = usePlantResource({
    plantId,
    fetcher: (id) => fetchMonthlyProductionHistory(id, HISTORY_LIMIT),
    parse: parseMonthlyProductionHistory,
    errorMessage: 'Erro ao buscar a conferência dos créditos.',
  })

  const loading = (savings.data === null && !savings.error) || (history.data === null && !history.error)
  const cycle = history.data?.cycles.find((item) => item.billId === billId) ?? null

  return (
    <section role="status" aria-live="polite" aria-label={`Resultado de ${cycleLabel}`} className={PANEL_CLASS}>
      <p className="font-semibold">Ciclo de {cycleLabel}</p>
      {loading ? (
        <p className="mt-2 text-[var(--color-text-secondary)]">Calculando o resultado deste ciclo...</p>
      ) : (
        <>
          <p className="mt-2">
            {savings.data?.savingsBrl != null ? (
              <>
                Você economizou <strong className="tabular-nums">{formatCurrency(savings.data.savingsBrl)}</strong>{' '}
                neste ciclo.
                <span className="ml-2 align-middle text-xs font-semibold text-[var(--color-chart-reference)]">
                  Estimado
                </span>
              </>
            ) : savings.data ? (
              savings.data.unavailableReason
                ? savingsUnavailableMessage(savings.data.unavailableReason)
                : 'Economia ainda não disponível para este ciclo.'
            ) : (
              'Economia ainda não disponível para este ciclo.'
            )}
          </p>
          <p className="mt-2 text-[var(--color-text-secondary)]">
            {cycle ? verdictDetail(cycle, distributorDisplayName(cycle.distributor)) : UNAVAILABLE_CHECK}
          </p>
        </>
      )}
      <Link to={DASHBOARD_PRODUCTION_PATH} className={LINK_CLASS}>
        Ver o ciclo
      </Link>
    </section>
  )
}

// Vários confirmados de uma vez: um resumo só, sem um painel por fatura.
export function ConfirmedBatchResult() {
  return (
    <section role="status" aria-live="polite" aria-label="Conferência dos ciclos confirmados" className={PANEL_CLASS}>
      <p>O veredito dos créditos de cada ciclo confirmado está em Energia.</p>
      <Link to={DASHBOARD_PRODUCTION_PATH} className={LINK_CLASS}>
        Ver os ciclos
      </Link>
    </section>
  )
}
