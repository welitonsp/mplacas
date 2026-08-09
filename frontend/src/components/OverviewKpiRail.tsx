import { Link } from 'react-router'
import type { MetricValue } from '../lib/dashboard/contracts'
import { savingsUnavailableMessage } from '../lib/dashboard/contracts'
import { formatCurrency, formatFullDate, formatNumber } from '../lib/format'
import { DASHBOARD_FINANCIAL_PATH, DASHBOARD_PRODUCTION_PATH } from '../routes'

type IconName = 'cycle' | 'latest' | 'savings'

function KpiIcon({ name }: { name: IconName }) {
  if (name === 'savings') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 7.5h14.5A1.5 1.5 0 0 1 20 9v8.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5v-11A1.5 1.5 0 0 1 5.5 5H17" />
        <path d="M16 12h4v3h-4a1.5 1.5 0 0 1 0-3Z" />
      </svg>
    )
  }

  if (name === 'latest') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M13 2 5.5 13h6L11 22l7.5-12h-6L13 2Z" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" />
    </svg>
  )
}

function KpiItem({
  icon,
  label,
  value,
  meta,
  to,
  accentClass,
}: {
  icon: IconName
  label: string
  value: string
  meta: string
  to: string
  accentClass: string
}) {
  return (
    <div className="group relative min-w-0 px-4 py-3.5 sm:px-5 sm:py-4">
      <div className="flex items-start gap-3">
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${accentClass}`}>
          <KpiIcon name={icon} />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
          <p className="mt-1 text-lg font-semibold tabular-nums tracking-tight text-gray-900 sm:text-xl">{value}</p>
          <p className="mt-1 text-xs leading-relaxed text-gray-500">{meta}</p>
        </div>
      </div>
      <Link
        to={to}
        className="mt-3 inline-flex min-h-[44px] items-center text-xs font-semibold text-[var(--color-brand-primary)] hover:text-[var(--color-brand-primary-dark)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
      >
        Ver detalhes <span aria-hidden="true" className="ml-1 transition-transform group-hover:translate-x-0.5">→</span>
      </Link>
    </div>
  )
}

export function OverviewKpiRail({
  cycleProduction,
  latestProduction,
  latestProductionDate,
  estimatedSavings,
  savingsUnavailableReason,
  referenceMonth,
}: {
  cycleProduction: MetricValue
  latestProduction: MetricValue
  latestProductionDate: string | null
  estimatedSavings: MetricValue
  savingsUnavailableReason: string | null
  referenceMonth: string
}) {
  const savingsAvailable = savingsUnavailableReason == null && estimatedSavings != null
  const savingsMeta = savingsAvailable
    ? `Estimativa para o ciclo ${referenceMonth}`
    : savingsUnavailableReason
      ? savingsUnavailableMessage(savingsUnavailableReason)
      : 'Economia estimada ainda não disponível para este ciclo.'

  return (
    <div
      role="group"
      aria-label="Resumo executivo do ciclo"
      className="grid divide-y divide-[var(--color-border)] border-t border-[var(--color-border)] bg-[var(--color-surface)]/75 sm:grid-cols-3 sm:divide-x sm:divide-y-0"
    >
      <KpiItem
        icon="cycle"
        label="Produção do ciclo"
        value={`${formatNumber(cycleProduction)} kWh`}
        meta={`Ciclo de referência ${referenceMonth}`}
        to={DASHBOARD_PRODUCTION_PATH}
        accentClass="bg-[var(--color-energy-solar-light)] text-[var(--color-energy-solar)]"
      />
      <KpiItem
        icon="latest"
        label="Último dia coletado"
        value={`${formatNumber(latestProduction)} kWh`}
        meta={latestProductionDate ? `Dado de ${formatFullDate(latestProductionDate)}` : 'Ainda sem produção diária disponível'}
        to={DASHBOARD_PRODUCTION_PATH}
        accentClass="bg-[var(--color-brand-primary-light)] text-[var(--color-energy-grid)]"
      />
      <KpiItem
        icon="savings"
        label="Economia estimada"
        value={savingsAvailable ? formatCurrency(estimatedSavings) : 'Indisponível'}
        meta={savingsMeta}
        to={DASHBOARD_FINANCIAL_PATH}
        accentClass="bg-[var(--color-data-secondary-light)] text-[var(--color-energy-consumption)]"
      />
    </div>
  )
}
