import type { MetricValue } from '../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../lib/format'
import { GRID_HEX } from '../lib/dashboard/visuals'

const DONUT_RADIUS = 46
const DONUT_CIRCUMFERENCE = 2 * Math.PI * DONUT_RADIUS

export function ConsumptionDonut({
  imported,
  selfConsumption,
}: {
  imported: MetricValue
  selfConsumption: MetricValue
}) {
  const imp = toNumber(imported)
  const sc = toNumber(selfConsumption)
  const total = (imp ?? 0) + (sc ?? 0)
  const hasData = imp != null && sc != null && total > 0

  if (!hasData) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Origem do consumo
        </p>
        <p className="mt-4 text-sm text-gray-400">Dados insuficientes para o gráfico.</p>
      </div>
    )
  }

  const imported_ = imp as number
  const selfConsumption_ = sc as number
  const importedPercent = (imported_ / total) * 100
  const selfConsumptionPercent = (selfConsumption_ / total) * 100

  const selfConsumptionLength = (selfConsumptionPercent / 100) * DONUT_CIRCUMFERENCE
  const importedLength = (importedPercent / 100) * DONUT_CIRCUMFERENCE

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Origem do consumo
      </p>

      <div className="mt-4 flex flex-col items-center gap-4 sm:flex-row sm:items-center">
        <svg
          viewBox="0 0 120 120"
          className="h-32 w-32 shrink-0"
          role="img"
          aria-label={`Origem do consumo: ${formatNumber(selfConsumption_)} kWh de autoconsumo (${formatNumber(
            selfConsumptionPercent,
            0
          )}%) e ${formatNumber(imported_)} kWh importados da concessionária (${formatNumber(
            importedPercent,
            0
          )}%), total de ${formatNumber(total)} kWh.`}
        >
          <circle cx="60" cy="60" r={DONUT_RADIUS} fill="none" stroke="#f3f4f6" strokeWidth="16" />
          <circle
            cx="60"
            cy="60"
            r={DONUT_RADIUS}
            fill="none"
            stroke="var(--color-brand-primary)"
            strokeWidth="16"
            strokeDasharray={`${selfConsumptionLength} ${DONUT_CIRCUMFERENCE}`}
            strokeDashoffset="0"
            transform="rotate(-90 60 60)"
          />
          <circle
            cx="60"
            cy="60"
            r={DONUT_RADIUS}
            fill="none"
            stroke={GRID_HEX}
            strokeWidth="16"
            strokeDasharray={`${importedLength} ${DONUT_CIRCUMFERENCE}`}
            strokeDashoffset={-selfConsumptionLength}
            transform="rotate(-90 60 60)"
          />
          <text
            x="60"
            y="56"
            textAnchor="middle"
            className="fill-gray-900 text-[16px] font-semibold"
          >
            {formatNumber(total, 0)}
          </text>
          <text x="60" y="72" textAnchor="middle" className="fill-gray-400 text-[10px]">
            kWh
          </text>
        </svg>

        {/* Alternativa textual acessível ao SVG — não depende só da cor/gráfico. */}
        <ul className="w-full space-y-2 text-sm text-gray-600">
          <li className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-[var(--color-brand-primary)]" />
            <span className="flex-1">Autoconsumo</span>
            <span className="font-medium text-gray-900">{formatNumber(selfConsumption_)} kWh</span>
            <span className="text-xs text-gray-400">({formatNumber(selfConsumptionPercent, 0)}%)</span>
          </li>
          <li className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-gray-300" />
            <span className="flex-1">Importada da concessionária</span>
            <span className="font-medium text-gray-900">{formatNumber(imported_)} kWh</span>
            <span className="text-xs text-gray-400">({formatNumber(importedPercent, 0)}%)</span>
          </li>
        </ul>
      </div>
    </div>
  )
}
