import { Link } from 'react-router'
import { ArrowUpRight } from 'lucide-react'
import type { MetricValue } from '../lib/dashboard/contracts'
import { savingsUnavailableMessage } from '../lib/dashboard/contracts'
import { formatCurrency, formatFullDate, formatNumber } from '../lib/format'
import { DASHBOARD_FINANCIAL_PATH, DASHBOARD_PRODUCTION_PATH } from '../routes'

// Natureza do número, sempre visível (skill `data-quality-ui`): medido vem da
// telemetria/fatura; calculado é derivado pelo motor; estimado é inferência.
// Sem valor, o selo diz POR QUÊ (carregando / indisponível) em vez de
// carimbar "Medido" num travessão.
type Nature = 'Medido' | 'Medido · parcial' | 'Calculado' | 'Estimado' | 'Carregando' | 'Indisponível'

const NATURE_CLASS: Record<Nature, string> = {
  Medido: 'bg-[var(--color-success-light)] text-[var(--color-success-text)]',
  'Medido · parcial': 'bg-[var(--color-warning-light)] text-[var(--color-warning-text)]',
  Calculado: 'border border-[var(--color-border)] text-[var(--color-text-secondary)]',
  Estimado: 'border border-dashed border-[var(--color-gray-400)] text-[var(--color-text-secondary)]',
  Carregando: 'bg-[var(--color-gray-100)] text-[var(--color-text-secondary)]',
  Indisponível: 'bg-[var(--color-gray-100)] text-[var(--color-text-secondary)]',
}

type DailyStatus = 'loading' | 'error' | 'ready'

function natureFor(value: unknown, nature: Nature, dailyStatus: DailyStatus = 'ready'): Nature {
  if (value != null) return nature
  if (dailyStatus === 'loading') return 'Carregando'
  return 'Indisponível'
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
  dailyStatus = 'ready',
  cyclePartial = false,
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
  // Estado do recurso diário (`/energy/anomalies/latest`), que alimenta
  // "Último dia" e "Desempenho": carregando/erro não é o mesmo que "sem dado".
  dailyStatus?: DailyStatus
  // Ciclo com dias ausentes/provisórios/incompletos: a soma do ciclo inclui
  // linhas provisórias, então "Medido" vira "Medido · parcial".
  cyclePartial?: boolean
}) {
  const savingsAvailable = savingsUnavailableReason == null && estimatedSavings != null
  const savingsMeta = savingsAvailable
    ? `Ciclo ${referenceMonth}`
    : savingsUnavailableReason
      ? savingsUnavailableMessage(savingsUnavailableReason)
      : 'Economia estimada ainda não disponível para este ciclo.'
  const dailyMeta = (ready: string) =>
    dailyStatus === 'loading'
      ? 'Carregando produção diária'
      : dailyStatus === 'error'
        ? 'Produção diária não carregou'
        : ready
  const cycleValue = cycleProduction == null || cycleProduction === '' ? null : cycleProduction
  const latestValue = latestProduction == null || latestProduction === '' ? null : latestProduction

  return (
    <div role="group" aria-label="Resumo executivo do ciclo" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
      <KpiCard
        label="Produção do ciclo"
        value={cycleValue == null ? '—' : formatNumber(cycleValue)}
        unit={cycleValue == null ? undefined : 'kWh'}
        nature={natureFor(cycleValue, cyclePartial ? 'Medido · parcial' : 'Medido')}
        meta={`Ciclo ${referenceMonth}`}
        to={DASHBOARD_PRODUCTION_PATH}
      />
      <KpiCard
        label="Último dia coletado"
        value={latestValue == null ? '—' : formatNumber(latestValue)}
        unit={latestValue == null ? undefined : 'kWh'}
        nature={natureFor(latestValue, 'Medido', dailyStatus)}
        meta={dailyMeta(latestProductionDate ? `Dado de ${formatFullDate(latestProductionDate)}` : 'Ainda sem produção diária')}
        to={DASHBOARD_PRODUCTION_PATH}
      />
      <KpiCard
        label="Desempenho vs esperado"
        value={performancePercent == null ? '—' : formatNumber(performancePercent, 1)}
        unit={performancePercent == null ? undefined : '%'}
        nature={natureFor(performancePercent, 'Calculado', dailyStatus)}
        meta={dailyMeta(
          performanceAssessedDays > 0
            ? `${performanceAssessedDays} ${performanceAssessedDays === 1 ? 'dia avaliado' : 'dias avaliados'}`
            : 'Sem esperado no recorte',
        )}
        to={DASHBOARD_PRODUCTION_PATH}
      />
      <KpiCard
        label="Economia estimada"
        value={savingsAvailable ? formatCurrency(estimatedSavings) : '—'}
        nature={savingsAvailable ? 'Estimado' : 'Indisponível'}
        meta={savingsMeta}
        to={DASHBOARD_FINANCIAL_PATH}
      />
    </div>
  )
}
