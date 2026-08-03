import type { MetricValue } from '../lib/dashboard/contracts'
import { clampPercent, formatNumber, toNumber } from '../lib/format'

export function EnergyFlowDiagram({
  production,
  selfConsumption,
  injected,
  imported,
  consumption,
}: {
  production: MetricValue
  selfConsumption: MetricValue
  injected: MetricValue
  imported: MetricValue
  consumption: MetricValue
}) {
  const prod = toNumber(production)
  const sc = toNumber(selfConsumption)
  const inj = toNumber(injected)
  const imp = toNumber(imported)
  const cons = toNumber(consumption)

  const hasData = prod != null && prod > 0 && cons != null && cons > 0 && sc != null && inj != null && imp != null

  if (!hasData) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Fluxo de energia no ciclo
        </p>
        <p className="mt-4 text-sm text-gray-500">Dados insuficientes para o diagrama.</p>
      </div>
    )
  }

  const production_ = prod as number
  const consumption_ = cons as number
  const selfConsumption_ = sc as number
  const injected_ = inj as number
  const imported_ = imp as number

  const prodAutoPercent = (selfConsumption_ / production_) * 100
  const prodExportPercent = (injected_ / production_) * 100
  const consAutoPercent = (selfConsumption_ / consumption_) * 100
  const consImportPercent = (imported_ / consumption_) * 100

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Fluxo de energia no ciclo
      </p>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto_1fr] sm:grid-rows-2 sm:items-center sm:gap-x-6 sm:gap-y-3">
        {/* Nó: Produção */}
        <div className="sm:col-start-1 sm:row-start-1 sm:row-span-2 rounded-lg border border-gray-100 bg-gray-50 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">Produção</p>
          <p className="mt-1 text-xl font-semibold text-gray-900">{formatNumber(production_)} kWh</p>
          <div
            className="mt-3 flex h-2 w-full overflow-hidden rounded-full bg-gray-100"
            role="progressbar"
            aria-valuenow={Math.round(clampPercent(prodAutoPercent))}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Produção: percentual autoconsumido"
          >
            <div
              className="h-full bg-[var(--color-brand-primary)]"
              style={{ width: `${clampPercent(prodAutoPercent)}%` }}
            />
            <div className="h-full bg-gray-300" style={{ width: `${clampPercent(prodExportPercent)}%` }} />
          </div>
          <ul className="mt-2 space-y-1 text-xs text-gray-600">
            <li className="flex items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--color-brand-primary)]" />
              Autoconsumo: <span className="font-medium text-gray-900">{formatNumber(selfConsumption_)} kWh</span>
            </li>
            <li className="flex items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-gray-300" />
              Exportada: <span className="font-medium text-gray-900">{formatNumber(injected_)} kWh</span>
            </li>
          </ul>
        </div>

        {/* Seta: autoconsumo direto (produção → consumo) */}
        <div className="flex items-center justify-center gap-2 text-center sm:col-start-2 sm:row-start-1">
          <span aria-hidden="true" className="text-lg text-[var(--color-brand-primary)] sm:hidden">
            ↓
          </span>
          <span aria-hidden="true" className="hidden text-lg text-[var(--color-brand-primary)] sm:inline">
            →
          </span>
          <span className="text-xs text-gray-500">
            autoconsumo
            <br />
            <span className="font-medium text-gray-900">{formatNumber(selfConsumption_)} kWh</span>
          </span>
        </div>

        {/* Nó: Rede (exportada entra, importada sai) */}
        <div className="rounded-lg border border-dashed border-gray-200 bg-white p-3 text-center sm:col-start-2 sm:row-start-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">Rede</p>
          <p className="mt-1 text-xs text-gray-600">
            <span aria-hidden="true">←</span> Exportada: <span className="font-medium text-gray-900">{formatNumber(injected_)} kWh</span>
          </p>
          <p className="mt-0.5 text-xs text-gray-600">
            Importada: <span className="font-medium text-gray-900">{formatNumber(imported_)} kWh</span> <span aria-hidden="true">→</span>
          </p>
        </div>

        {/* Nó: Consumo */}
        <div className="sm:col-start-3 sm:row-start-1 sm:row-span-2 rounded-lg border border-gray-100 bg-gray-50 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">Consumo</p>
          <p className="mt-1 text-xl font-semibold text-gray-900">{formatNumber(consumption_)} kWh</p>
          <div
            className="mt-3 flex h-2 w-full overflow-hidden rounded-full bg-gray-100"
            role="progressbar"
            aria-valuenow={Math.round(clampPercent(consAutoPercent))}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Consumo: percentual autossuprido"
          >
            <div
              className="h-full bg-[var(--color-brand-primary)]"
              style={{ width: `${clampPercent(consAutoPercent)}%` }}
            />
            <div className="h-full bg-gray-300" style={{ width: `${clampPercent(consImportPercent)}%` }} />
          </div>
          <ul className="mt-2 space-y-1 text-xs text-gray-600">
            <li className="flex items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--color-brand-primary)]" />
              Autoconsumo: <span className="font-medium text-gray-900">{formatNumber(selfConsumption_)} kWh</span>
            </li>
            <li className="flex items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full bg-gray-300" />
              Importada: <span className="font-medium text-gray-900">{formatNumber(imported_)} kWh</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  )
}
