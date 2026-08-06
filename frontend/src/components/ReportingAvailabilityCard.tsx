import type { PerformanceUnavailableReason, PhotovoltaicPerformanceLatest } from '../lib/dashboard/photovoltaic-contracts'
import { performanceUnavailableMessage, ratioToPercent } from '../lib/dashboard/photovoltaic-contracts'
import { performanceSeverity } from '../lib/dashboard/visuals'
import { formatNumber } from '../lib/format'
import { Card } from './Card'
import { Gauge } from './charts/Gauge'

// `reporting_availability_ratio` é disponibilidade de REPORTE de dados (quantos
// devices enviaram medição), não disponibilidade técnica dos equipamentos —
// ADR-065 seção 3 é explícito sobre não confundir os dois. O rótulo diz
// "de reporte" para não sugerir uptime de inversor.
export function ReportingAvailabilityCard({
  performance,
  unavailableReason,
}: {
  performance: PhotovoltaicPerformanceLatest | null
  unavailableReason: PerformanceUnavailableReason | null
}) {
  if (performance === null) {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Disponibilidade de reporte</p>
        <p className="mt-4 text-sm text-gray-500">
          {performanceUnavailableMessage(unavailableReason ?? 'NO_PERFORMANCE_RESULTS')}
        </p>
      </Card>
    )
  }

  const availability = ratioToPercent(performance.reporting_availability_ratio)

  if (availability === null) {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Disponibilidade de reporte</p>
        <p className="mt-2 text-sm text-gray-500">{formatNumber(availability)}</p>
        <p className="mt-1 text-xs text-gray-500">
          Fração de devices que enviaram dados no dia — não é o uptime dos equipamentos.
        </p>
      </Card>
    )
  }

  return (
    <Card>
      <div className="mt-1">
        <Gauge
          value={availability}
          label="Disponibilidade de reporte"
          valueLabel={`${formatNumber(availability, 0)}%`}
          tone={performanceSeverity(availability)}
          size={72}
        />
      </div>
      <p className="mt-2 text-xs text-gray-500">
        Fração de devices que enviaram dados no dia — não é o uptime dos equipamentos.
      </p>
    </Card>
  )
}
