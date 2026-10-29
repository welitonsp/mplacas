import { Link } from 'react-router'
import type { ExecutiveIndicators } from '../../lib/dashboard/contracts'
import { savingsUnavailableMessage } from '../../lib/dashboard/contracts'
import type { FinancialReturnResponse } from '../../lib/dashboard/financial-return-contracts'
import {
  financialReturnUnavailableMessage,
  isPaybackAlreadyReached,
} from '../../lib/dashboard/financial-return-contracts'
import { formatCurrency, formatCycleLabel, formatNumber, toNumber } from '../../lib/format'
import { DASHBOARD_FINANCIAL_PATH } from '../../routes'

const LINK_CLASS =
  'inline-flex min-h-[44px] items-center gap-1 rounded text-sm font-semibold text-[var(--color-brand-primary)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]'

// Retorno acumulado — só o que o backend já calculou (ADR-067). A barra usa o
// próprio `roi_percent` (economia acumulada ÷ investimento), limitada a 100%.
function ReturnProgress({ result }: { result: FinancialReturnResponse | null }) {
  if (result == null) return null
  if (result.unavailable_reason) {
    return (
      <p className="border-t border-[var(--color-border)] pt-3 text-[13px] leading-5 text-[var(--color-text-secondary)]">
        {financialReturnUnavailableMessage(result.unavailable_reason)}
      </p>
    )
  }
  const roi = toNumber(result.roi_percent)
  if (roi == null) return null
  const reached = isPaybackAlreadyReached(result)
  return (
    <div className="flex flex-col gap-1.5 border-t border-[var(--color-border)] pt-3">
      <div className="flex justify-between gap-3 text-[13px]">
        <span className="text-[var(--color-text-secondary)]">
          {reached ? 'Investimento já recuperado' : 'Investimento recuperado até agora'}
        </span>
        <span className="font-semibold tabular-nums text-[var(--color-text-primary)]">{formatNumber(roi, 0)}%</span>
      </div>
      <div
        role="img"
        aria-label={`${formatNumber(roi, 1)}% do investimento já voltou em economia`}
        className="h-2 overflow-hidden rounded-full bg-[var(--color-chart-track)]"
      >
        <div className="h-full rounded-full bg-[var(--color-energy-solar)]" style={{ width: `${Math.min(100, Math.max(2, roi))}%` }} />
      </div>
      <p className="text-xs text-[var(--color-text-secondary)]">
        {`${formatCurrency(result.accumulated_savings_brl)} economizados de ${formatCurrency(result.investment_amount_brl)} investidos`}
      </p>
    </div>
  )
}

// Cartão de dinheiro do Início (ADR-083): economia do último ciclo com fatura,
// a conta com e sem a usina e quanto do investimento já voltou. Os detalhes
// (tarifa, créditos, CDI) moram na aba Dinheiro.
//
// Selo "Estimado": a economia combina a fatura com a produção do inversor
// (autoconsumo), então não é "pela fatura". Ciclo com dia sem leitura ou em
// consolidação vira "Estimado · ciclo parcial" — o valor pode estar abaixo do
// real (ver `buildCalmNote`).
export function HomeSavingsCard({
  indicators,
  referenceMonth,
  financialReturn,
  partial,
}: {
  indicators: ExecutiveIndicators
  referenceMonth: string
  financialReturn: FinancialReturnResponse | null
  partial: boolean
}) {
  const savings = toNumber(indicators.estimated_savings_brl)
  const withoutSolar = toNumber(indicators.bill_without_solar_brl ?? null)
  const paid = toNumber(indicators.total_amount_brl)
  const cycle = formatCycleLabel(referenceMonth)

  return (
    <section
      aria-labelledby="home-savings-heading"
      className="flex flex-col gap-3.5 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="home-savings-heading" className="text-[14px] font-medium text-[var(--color-text-secondary)]">
          Você economizou em {cycle}
        </h2>
        <span className="shrink-0 rounded-full bg-[var(--color-gray-100)] px-2 py-0.5 text-xs font-semibold text-[var(--color-chart-reference)]">
          {partial ? 'Estimado · ciclo parcial' : 'Estimado'}
        </span>
      </div>

      {savings == null ? (
        <p className="text-[15px] leading-6 text-[var(--color-text-secondary)]">
          {indicators.savings_unavailable_reason
            ? savingsUnavailableMessage(indicators.savings_unavailable_reason)
            : 'Economia ainda não disponível para este ciclo.'}
        </p>
      ) : (
        <>
          <p className="font-display text-[40px] font-semibold leading-none tabular-nums text-[var(--color-success-text)]">
            {formatCurrency(savings)}
          </p>
          {withoutSolar != null && paid != null && (
            <dl className="grid grid-cols-2 gap-3">
              <div>
                <dt className="text-xs text-[var(--color-text-secondary)]">Sem a usina</dt>
                <dd className="text-[16px] font-semibold tabular-nums text-[var(--color-text-secondary)] line-through">
                  {formatCurrency(withoutSolar)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-secondary)]">Você pagou</dt>
                <dd className="text-[16px] font-semibold tabular-nums text-[var(--color-text-primary)]">{formatCurrency(paid)}</dd>
              </div>
            </dl>
          )}
        </>
      )}

      <ReturnProgress result={financialReturn} />

      <Link to={DASHBOARD_FINANCIAL_PATH} className={`${LINK_CLASS} mt-auto self-start`}>
        Ver meu dinheiro <span aria-hidden="true">→</span>
      </Link>
    </section>
  )
}
