import type { MetricValue } from '../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../lib/format'

export function ProductionSplitCard({
  selfConsumption,
  injected,
}: {
  selfConsumption: MetricValue
  injected: MetricValue
}) {
  const sc = toNumber(selfConsumption)
  const inj = toNumber(injected)
  const total = (sc ?? 0) + (inj ?? 0)
  const hasData = sc != null && inj != null && total > 0

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Composição da produção
      </p>
      {!hasData ? (
        <p className="mt-4 text-sm text-gray-400">Dados insuficientes para o gráfico.</p>
      ) : (
        <>
          <div className="mt-4 flex h-3 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full bg-[var(--color-brand-primary)]"
              style={{ width: `${((sc as number) / total) * 100}%` }}
            />
            <div className="h-full bg-gray-300" style={{ width: `${((inj as number) / total) * 100}%` }} />
          </div>
          <div className="mt-3 space-y-1.5 text-xs text-gray-600">
            <p className="flex flex-wrap items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--color-brand-primary)]" />
              Autoconsumo:
              <span className="font-medium text-gray-900">{formatNumber(sc)} kWh</span>
              <span className="text-gray-400">
                ({formatNumber(((sc as number) / total) * 100, 0)}%)
              </span>
            </p>
            <p className="flex flex-wrap items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-gray-300" />
              Injetada na rede:
              <span className="font-medium text-gray-900">{formatNumber(inj)} kWh</span>
              <span className="text-gray-400">
                ({formatNumber(((inj as number) / total) * 100, 0)}%)
              </span>
            </p>
          </div>
        </>
      )}
    </div>
  )
}
