import { Link } from 'react-router'
import { ArrowUpRight } from 'lucide-react'
import type { MetricValue } from '../lib/dashboard/contracts'
import { savingsUnavailableMessage } from '../lib/dashboard/contracts'
import { formatCurrency, formatFullDate, formatNumber } from '../lib/format'
import { DASHBOARD_FINANCIAL_PATH, DASHBOARD_PRODUCTION_PATH } from '../routes'

// Natureza do número, sempre visível (skill `data-quality-ui`): medido vem da
// telemetria/fatura; calculado é derivado pelo motor; estimado é inferência.
type Nature = 'Medido' | 'Calculado' | 'Estimado'

const NATURE_CLASS: Record<Nature, string> = {
  Medido: 'bg-[var(--color-success-light)] text-[var(--color-success-text)]',
  Calculado: 'border border-[var(--color-border)] text-[var(--color-text-secondary)]',
  Estimado: 'border border-dashed border-[var(--color-gray-400)] text-[var(--color-text-secondary)]',
}

function KpiCard({
  label,
  value,
  unit,
  nature,
  meta,
  to,
}: {
  label: string
  value: string
  unit?: string
  nature: Nature
  meta: string
  to: string
}) {
  return (
    <Link
      to={to}
      className="group flex min-w-0 flex-col rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-[var(--shadow-card)] transition-colors duration-150 hover:border-[var(--color-gray-300)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none sm:p-5"
    >
      <span className="flex items-start justify-between gap-2">
        <span className="text-[13px] font-medium leading-5 text-[var(--color-text-secondary)]">{label}</span>
        <ArrowUpRight
          aria-hidden="true"
          className="h-4 w-4 shrink-0 text-[var(--color-text-secondary)] opacity-60 transition-opacity group-hover:opacity-100"
        />
      </span>
      <span className="mt-1.5 flex flex-wrap items-baseline gap-x-1.5">
        <span className="font-display text-[24px] font-semibold leading-tight tracking-[-0.02em] tabular-nums text-[var(--color-text-primary)] sm:text-[30px]">
          {value}
        </span>
        {unit && <span className="text-sm font-medium text-[var(--color-text-secondary)]">{unit}</span>}
      </span>
      <span className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-3">
        <span className={`rounded-md px-1.5 py-0.5 text-[11.5px] font-semibold ${NATURE_CLASS[nature]}`}>{nature}</span>
        <span className="text-[12.5px] leading-5 text-[var(--color-text-secondary)]">{meta}</span>
      </span>
      <span className="sr-only">Ver detalhes</span>
    </Link>
  )
}

// Linha de indicadores da Visão Geral (ADR-077, etapa 4): quatro cartões
// iguais logo abaixo do resumo, cada um levando ao módulo que explica o
// número. Antes eram três itens espremidos no rodapé do resumo, e o
// "Desempenho vs esperado" ficava num quadro à parte, repetindo "Último dia".
export function OverviewKpiRail({
  cycleProduction,
  latestProduction,
  latestProductionDate,
  estimatedSavings,
  savingsUnavailableReason,
  referenceMonth,
  performancePercent = null,
  performanceAssessedDays = 0,
}: {
  cycleProduction: MetricValue
  latestProduction: MetricValue
  latestProductionDate: string | null
  estimatedSavings: MetricValue
  savingsUnavailableReason: string | null
  referenceMonth: string
  // Desempenho real vs esperado no recorte recente (calculado em
  // `productionPerformancePercent`, nunca aqui).
  performancePercent?: number | null
  performanceAssessedDays?: number
}) {
  const savingsAvailable = savingsUnavailableReason == null && estimatedSavings != null
  const savingsMeta = savingsAvailable
    ? `Ciclo ${referenceMonth}`
    : savingsUnavailableReason
      ? savingsUnavailableMessage(savingsUnavailableReason)
      : 'Economia estimada ainda não disponível para este ciclo.'

  return (
    <div role="group" aria-label="Resumo executivo do ciclo" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
      <KpiCard
        label="Produção do ciclo"
        value={formatNumber(cycleProduction)}
        unit="kWh"
        nature="Medido"
        meta={`Ciclo ${referenceMonth}`}
        to={DASHBOARD_PRODUCTION_PATH}
      />
      <KpiCard
        label="Último dia coletado"
        value={formatNumber(latestProduction)}
        unit="kWh"
        nature="Medido"
        meta={latestProductionDate ? `Dado de ${formatFullDate(latestProductionDate)}` : 'Ainda sem produção diária'}
        to={DASHBOARD_PRODUCTION_PATH}
      />
      <KpiCard
        label="Desempenho vs esperado"
        value={performancePercent == null ? '—' : formatNumber(performancePercent, 1)}
        unit={performancePercent == null ? undefined : '%'}
        nature="Calculado"
        meta={
          performanceAssessedDays > 0
            ? `${performanceAssessedDays} ${performanceAssessedDays === 1 ? 'dia avaliado' : 'dias avaliados'}`
            : 'Sem esperado no recorte'
        }
        to={DASHBOARD_PRODUCTION_PATH}
      />
      <KpiCard
        label="Economia estimada"
        value={savingsAvailable ? formatCurrency(estimatedSavings) : 'Indisponível'}
        nature="Estimado"
        meta={savingsMeta}
        to={DASHBOARD_FINANCIAL_PATH}
      />
    </div>
  )
}
