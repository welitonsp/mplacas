import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'
import { baselineUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { formatNumber } from '../lib/format'

// Companheiro direto de "Produção no ciclo" (ver `DashboardPage`) — os dois
// ficam sempre no mesmo container visual para que o dono da usina compare
// real vs. esperado sem rolar a página até o histórico. `kwh` aqui é uma
// média diária (baseline sazonal, ver ADR-065), não o total do ciclo — o
// rótulo deixa isso explícito para não comparar grandezas diferentes.
export function ExpectedProductionCard({
  expectedProduction,
}: {
  expectedProduction: ExpectedDailyProduction | null
}) {
  if (expectedProduction === null) {
    return (
      <div className="animate-pulse rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="mb-3 h-3 w-1/3 rounded bg-gray-200" />
        <div className="h-8 w-1/2 rounded bg-gray-100" />
      </div>
    )
  }

  if (!expectedProduction.available) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Produção esperada</p>
        <p className="mt-4 text-sm text-gray-500">
          {baselineUnavailableMessage(expectedProduction.reason, expectedProduction.referenceCompleteOn)}
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Produção esperada (média diária)
      </p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">
        {formatNumber(expectedProduction.kwh)}
        <span className="ml-1 text-sm font-normal text-gray-500">kWh/dia</span>
      </p>
    </div>
  )
}
