import type { AnomalyDailyPoint } from '../lib/dashboard/contracts'
import { formatNumber, formatShortDate } from '../lib/format'
import { computeYieldStats, YIELD_ATYPICAL_THRESHOLD_PERCENT } from '../lib/dashboard/yield'

export function YieldCard({ daily }: { daily: AnomalyDailyPoint[] }) {
  const { periodYield, days } = computeYieldStats(daily)

  // Sem irradiância disponível (usina sem coordenadas configuradas), o card
  // simplesmente não existe — rendimento não faz sentido sem o denominador.
  if (periodYield == null) return null

  const atypicalDays = days
    .filter((d) => Math.abs(d.deviationPercent) >= YIELD_ATYPICAL_THRESHOLD_PERCENT)
    .sort((a, b) => Math.abs(b.deviationPercent) - Math.abs(a.deviationPercent))
    .slice(0, 3)

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Rendimento do período
      </p>
      <p className="mt-1 text-[11px] text-gray-400">kWh gerados por kWh/m² de sol recebido</p>
      <p className="mt-2 text-2xl font-semibold text-[var(--color-data-secondary)]">
        {formatNumber(periodYield, 2)}
        <span className="ml-1 text-sm font-normal text-gray-500">kWh/kWh·m²</span>
      </p>

      {atypicalDays.length === 0 ? (
        <p className="mt-4 text-xs text-gray-500">
          Rendimento estável — nenhum dia com desvio relevante em relação à média do período.
        </p>
      ) : (
        <>
          <p className="mt-4 text-xs font-medium uppercase tracking-wide text-gray-500">
            Dias com rendimento fora do padrão
          </p>
          <ul className="mt-2 space-y-2 text-xs text-gray-600">
            {atypicalDays.map((d) => (
              <li key={d.date} className="flex items-center justify-between gap-2">
                <span className="font-medium text-gray-900">{formatShortDate(d.date)}</span>
                <span>
                  {d.deviationPercent > 0 ? 'acima' : 'abaixo'} da média em{' '}
                  <strong className="text-gray-900">{formatNumber(Math.abs(d.deviationPercent), 0)}%</strong>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] text-gray-400">
            Rendimento bem abaixo da média com sol disponível costuma indicar problema real na
            usina; bem acima costuma indicar dia de céu limpo apesar de pouca produção esperada.
          </p>
        </>
      )}
    </div>
  )
}
