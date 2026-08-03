import type { MetricValue } from '../lib/dashboard/contracts'
import { clampPercent, formatNumber, toNumber } from '../lib/format'
import { SEVERITY_BAR, SEVERITY_BG, SEVERITY_BORDER_L, SEVERITY_DOT, SEVERITY_TEXT, statusMeta } from '../lib/dashboard/visuals'

export function HeroCard({
  referenceMonth,
  headline,
  status,
  healthScore,
}: {
  referenceMonth: string
  headline: string
  status: string
  healthScore: MetricValue
}) {
  const meta = statusMeta(status)
  const score = toNumber(healthScore)

  return (
    <div
      className={`rounded-xl border border-gray-200 border-l-4 ${SEVERITY_BORDER_L[meta.severity]} bg-white p-5 shadow-sm sm:p-6`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Ciclo de referência: {referenceMonth}
          </p>
          <p className="mt-1 text-xl font-semibold text-gray-900">{headline}</p>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 self-start rounded-full px-3 py-1 text-xs font-semibold ${SEVERITY_BG[meta.severity]} ${SEVERITY_TEXT[meta.severity]}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${SEVERITY_DOT[meta.severity]}`} />
          {meta.label}
        </span>
      </div>

      {score != null && (
        <div className="mt-5">
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span className="font-medium uppercase tracking-wide">Saúde da usina</span>
            <span className={`font-semibold ${SEVERITY_TEXT[meta.severity]}`}>
              {formatNumber(score, 0)}/100
            </span>
          </div>
          <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className={`h-full rounded-full ${SEVERITY_BAR[meta.severity]}`}
              style={{ width: `${clampPercent(score)}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
