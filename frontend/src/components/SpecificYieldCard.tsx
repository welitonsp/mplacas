import type { PerformanceUnavailableReason, PhotovoltaicPerformanceLatest } from '../lib/dashboard/photovoltaic-contracts'
import { performanceUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { formatNumber, toNumber } from '../lib/format'
import { Card } from './Card'

// Yield específico (`final_yield_kwh_per_kwp`) normaliza a produção pela
// capacidade instalada — a métrica que permite comparar o desempenho da usina
// entre dias e com outras usinas, independente do tamanho (ver ADR-059).
// Unidade sempre visível (kWh/kWp), nunca um número solto (skill frontend-design).
export function SpecificYieldCard({
  performance,
  unavailableReason,
}: {
  performance: PhotovoltaicPerformanceLatest | null
  unavailableReason: PerformanceUnavailableReason | null
}) {
  if (performance === null) {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Yield específico</p>
        <p className="mt-4 text-sm text-gray-500">
          {performanceUnavailableMessage(unavailableReason ?? 'NO_PERFORMANCE_RESULTS')}
        </p>
      </Card>
    )
  }

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Yield específico</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900 tabular-nums">
        {formatNumber(toNumber(performance.final_yield_kwh_per_kwp))}
        <span className="ml-1 text-sm font-normal text-gray-500">kWh/kWp</span>
      </p>
    </Card>
  )
}
