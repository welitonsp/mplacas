import { Link } from 'react-router'
import type { WeekDay } from '../../lib/dashboard/home'
import { formatNumber, formatShortDate } from '../../lib/format'
import { DASHBOARD_PRODUCTION_PATH } from '../../routes'

// Produção dos 7 dias de calendário até a última leitura, no Início (ADR-083).
// Só o medido: desvio contra o esperado, irradiância e rendimento ficam na aba
// Energia. Dia sem leitura aparece como coluna vazia "sem dado" e o total diz
// quantos dias somou — nunca soma 5 dias como se fossem 7.
// Altura útil da barra mais alta: h-28 (112 px) menos o rótulo do valor (~16 px)
// e o espaço entre os dois.
const BAR_MAX_PX = 88

export function HomeWeekCard({ week }: { week: readonly WeekDay[] }) {
  const measured = week.filter((day): day is WeekDay & { kwh: number } => day.kwh != null)
  const total = measured.reduce((sum, day) => sum + day.kwh, 0)
  const average = measured.length > 0 ? total / measured.length : null
  const max = Math.max(...measured.map((day) => day.kwh), 1)
  const missing = week.length - measured.length
  const first = week[0]?.date
  const last = week[week.length - 1]?.date

  const summary = week
    .map((day) => `${formatShortDate(day.date)}: ${day.kwh == null ? 'sem dado' : `${formatNumber(day.kwh, 1)} kWh`}`)
    .join('; ')

  return (
    <section
      aria-labelledby="home-week-heading"
      className="flex flex-col gap-3.5 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="home-week-heading" className="text-[14px] font-medium text-[var(--color-text-secondary)]">
          {first && last ? `Gerou de ${formatShortDate(first)} a ${formatShortDate(last)}` : 'Produção recente'}
        </h2>
        <span className="shrink-0 rounded-full bg-[var(--color-gray-100)] px-2 py-0.5 text-xs font-semibold text-[var(--color-chart-reference)]">
          Medido
        </span>
      </div>

      {measured.length === 0 ? (
        <p className="text-[15px] leading-6 text-[var(--color-text-secondary)]">Ainda sem produção diária registrada nestes dias.</p>
      ) : (
        <>
          <div className="flex flex-col gap-1">
            <p className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-display text-[32px] font-semibold leading-none tabular-nums text-[var(--color-text-primary)]">
                {formatNumber(total, 0)}
              </span>
              <span className="text-[15px] text-[var(--color-text-secondary)]">
                {average == null ? 'kWh' : `kWh · média ${formatNumber(average, 1)} por dia`}
              </span>
            </p>
            {missing > 0 && (
              <p className="text-[13px] text-[var(--color-text-secondary)]">
                {missing === 1
                  ? `Soma de ${measured.length} dias: 1 dia ficou sem leitura.`
                  : `Soma de ${measured.length} dias: ${missing} dias ficaram sem leitura.`}
              </p>
            )}
          </div>
          <div role="img" aria-label={`Produção diária: ${summary}`}>
            {/* Valor de cada dia sobre a barra (chart-standards, regra 2: sem
                escala, barra não é dado). Unidade dita uma vez, acima. Dia sem
                leitura continua tracejado e sem número — nunca um 0 fabricado. */}
            <p className="mb-1 text-xs text-[var(--color-text-secondary)]" aria-hidden="true">
              kWh por dia
            </p>
            <div className="flex h-28 items-end gap-2" aria-hidden="true">
              {week.map((day) => (
                <div key={day.date} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
                  {day.kwh == null ? (
                    <span
                      data-testid="home-week-gap"
                      className="h-1.5 w-full max-w-8 rounded-full border border-dashed border-[var(--color-gray-400)]"
                    />
                  ) : (
                    <>
                      <span
                        data-testid="home-week-value"
                        className="text-xs font-semibold tabular-nums text-[var(--color-text-primary)]"
                      >
                        {formatNumber(day.kwh, 0)}
                      </span>
                      <span
                        data-testid="home-week-bar"
                        className="w-full max-w-8 rounded-t-md bg-[var(--color-energy-solar)]"
                        style={{ height: `${Math.max(4, Math.round((day.kwh / max) * BAR_MAX_PX))}px` }}
                      />
                    </>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-1.5 flex gap-2" aria-hidden="true">
              {week.map((day) => (
                <span key={day.date} className="min-w-0 flex-1 text-center text-xs tabular-nums text-[var(--color-text-secondary)]">
                  {formatShortDate(day.date)}
                </span>
              ))}
            </div>
            {missing > 0 && (
              <p className="mt-2 flex items-center gap-2 text-xs text-[var(--color-text-secondary)]" aria-hidden="true">
                <span className="h-1.5 w-4 rounded-full border border-dashed border-[var(--color-gray-400)]" />
                Sem leitura do inversor
              </p>
            )}
          </div>
        </>
      )}

      <Link
        to={DASHBOARD_PRODUCTION_PATH}
        className="mt-auto inline-flex min-h-[44px] items-center gap-1 self-start rounded text-sm font-semibold text-[var(--color-brand-primary)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
      >
        Ver minha energia <span aria-hidden="true">→</span>
      </Link>
    </section>
  )
}
