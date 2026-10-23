import { Link } from 'react-router'
import type { AnomalyDailyPoint } from '../../lib/dashboard/contracts'
import {
  DEFAULT_PRODUCTION_PERIOD_DAYS,
  averageActualProduction,
  latestProductionDays,
} from '../../lib/dashboard/production-alerts'
import { formatNumber, formatShortDate, toNumber } from '../../lib/format'
import { DASHBOARD_PRODUCTION_PATH } from '../../routes'

// Produção dos últimos 7 dias no Início (ADR-083). Só o medido: o desvio
// contra o esperado, a irradiância e o rendimento ficam na aba Energia.
// Dia sem leitura aparece como coluna vazia rotulada "sem dado", nunca zero.
export function HomeWeekCard({ daily }: { daily: readonly AnomalyDailyPoint[] }) {
  const recent = latestProductionDays(daily, DEFAULT_PRODUCTION_PERIOD_DAYS)
  const values = recent.map((day) => toNumber(day.actual_production_kwh))
  const measured = values.filter((value): value is number => value != null)
  const total = measured.reduce((sum, value) => sum + value, 0)
  const average = averageActualProduction(recent)
  const max = Math.max(...measured, 1)

  const summary = recent
    .map((day, index) => {
      const value = values[index]
      return `${formatShortDate(day.date)}: ${value == null ? 'sem dado' : `${formatNumber(value, 1)} kWh`}`
    })
    .join('; ')

  return (
    <section
      aria-labelledby="home-week-heading"
      className="flex flex-col gap-3.5 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="home-week-heading" className="text-[14px] font-medium text-[var(--color-text-secondary)]">
          Gerou nos últimos {recent.length} dias
        </h2>
        <span className="shrink-0 rounded-full bg-[var(--color-gray-100)] px-2 py-0.5 text-xs font-semibold text-[var(--color-chart-reference)]">
          Medido
        </span>
      </div>

      {measured.length === 0 ? (
        <p className="text-[15px] leading-6 text-[var(--color-text-secondary)]">
          Ainda sem produção diária registrada nestes dias.
        </p>
      ) : (
        <>
          <p className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-display text-[32px] font-semibold leading-none tabular-nums text-[var(--color-text-primary)]">
              {formatNumber(total, 0)}
            </span>
            <span className="text-[15px] text-[var(--color-text-secondary)]">
              {average.average == null ? 'kWh' : `kWh · média ${formatNumber(average.average, 1)} por dia`}
            </span>
          </p>
          <div role="img" aria-label={`Produção diária: ${summary}`}>
            <div className="flex h-24 items-end gap-2" aria-hidden="true">
              {recent.map((day, index) => {
                const value = values[index]
                const height = value == null ? 0 : Math.max(6, Math.round((value / max) * 100))
                return (
                  <div key={day.date} className="flex h-full min-w-0 flex-1 items-end justify-center">
                    {value == null ? (
                      <span className="h-1.5 w-full max-w-8 rounded-full border border-dashed border-[var(--color-gray-400)]" />
                    ) : (
                      <span
                        data-testid="home-week-bar"
                        className="w-full max-w-8 rounded-t-md bg-[var(--color-energy-solar)]"
                        style={{ height: `${height}%` }}
                      />
                    )}
                  </div>
                )
              })}
            </div>
            <div className="mt-1.5 flex gap-2" aria-hidden="true">
              {recent.map((day) => (
                <span key={day.date} className="min-w-0 flex-1 text-center text-[11px] tabular-nums text-[var(--color-text-secondary)]">
                  {formatShortDate(day.date)}
                </span>
              ))}
            </div>
          </div>
        </>
      )}

      <Link
        to={DASHBOARD_PRODUCTION_PATH}
        className="inline-flex min-h-[44px] items-center gap-1 self-start rounded text-sm font-semibold text-[var(--color-brand-primary)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
      >
        Ver minha energia <span aria-hidden="true">→</span>
      </Link>
    </section>
  )
}
