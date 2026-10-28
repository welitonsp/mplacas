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
        <p className="text-xs font-medium text-gray-500">Yield específico</p>
        <p className="mt-4 text-sm text-gray-500">
          {performanceUnavailableMessage(unavailableReason ?? 'NO_PERFORMANCE_RESULTS')}
        </p>
      </Card>
    )
  }

  return (
    <Card>
      <p className="text-[13px] font-medium leading-5 text-[var(--color-text-secondary)]">Yield específico</p>
      {/* Altura do anel (72 px) para alinhar com os vizinhos da grade. */}
      <p className="mt-3 flex min-h-[72px] items-center text-[28px] font-semibold leading-none text-[var(--color-text-primary)] tabular-nums">
        {formatNumber(toNumber(performance.final_yield_kwh_per_kwp))}
        <span className="ml-1.5 text-sm font-normal text-[var(--color-text-secondary)]">kWh/kWp</span>
      </p>
      <p className="mt-3 text-xs leading-5 text-[var(--color-text-secondary)]">
        Energia gerada por kWp instalado. Serve para comparar com usinas de outro tamanho.
      </p>
    </Card>
  )
}
