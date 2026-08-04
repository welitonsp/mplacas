import type {
  BaselineUnavailableReason,
  PhotovoltaicBaselineLatest,
} from '../lib/dashboard/photovoltaic-contracts'
import { baselineUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { formatNumber, toNumber } from '../lib/format'
import { Card } from './Card'

const DEGRADATION_STATUS_LABEL: Record<string, string> = {
  STABLE: 'Estável',
  WATCH: 'Observação',
  DEGRADED: 'Degradação confirmada',
}

// Degradação anualizada (`annualized_degradation_percent`) só existe quando há
// pelo menos 180 dias de separação entre os midpoints de referência e
// comparação (`seasonal_baseline.py`) — por isso é nullable mesmo com baseline
// disponível, e mostramos esse caso como "ainda em formação" em vez de
// esconder o card. Reaproveita a mesma mensagem de indisponibilidade de
// baseline da Etapa 1 quando o bloco inteiro está ausente.
export function BaselineDegradationCard({
  baseline,
  unavailableReason,
  referenceCompleteOn,
}: {
  baseline: PhotovoltaicBaselineLatest | null
  unavailableReason: BaselineUnavailableReason | null
  referenceCompleteOn: string | null
}) {
  if (baseline === null) {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Degradação anualizada</p>
        <p className="mt-4 text-sm text-gray-500">
          {baselineUnavailableMessage(unavailableReason ?? 'NO_PERFORMANCE_HISTORY', referenceCompleteOn)}
        </p>
      </Card>
    )
  }

  const annualized = toNumber(baseline.annualized_degradation_percent)
  const statusLabel = baseline.degradation_status
    ? (DEGRADATION_STATUS_LABEL[baseline.degradation_status] ?? baseline.degradation_status)
    : null

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Degradação anualizada</p>
      {annualized === null ? (
        <p className="mt-4 text-sm text-gray-500">
          Ainda não disponível — são necessários pelo menos 180 dias entre o período de
          referência e o de comparação para calcular a taxa anualizada.
        </p>
      ) : (
        <>
          <p className="mt-2 text-2xl font-semibold text-gray-900">
            {formatNumber(annualized)}
            <span className="ml-1 text-sm font-normal text-gray-500">%/ano</span>
          </p>
          {statusLabel && <p className="mt-1 text-xs text-gray-500">{statusLabel}</p>}
        </>
      )}
    </Card>
  )
}
