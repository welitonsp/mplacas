import type { PhotovoltaicSummaryResponse } from '../lib/dashboard/photovoltaic-contracts'
import { BaselineDegradationCard } from './BaselineDegradationCard'
import { LossBreakdownSection } from './LossBreakdownSection'
import { MetricCardSkeletonGrid } from './MetricCardSkeletonGrid'
import { PerformanceRatioCard } from './PerformanceRatioCard'
import { ReportingAvailabilityCard } from './ReportingAvailabilityCard'
import { SpecificYieldCard } from './SpecificYieldCard'

// Bloco próprio ("Como está o desempenho técnico?"), separado do Bloco 1
// ("Está indo bem?"): PR, yield específico, disponibilidade de reporte,
// degradação e atribuição de causa de perda respondem a mesma pergunta de
// alto nível, mas com granularidade técnica que um dono de usina leigo não
// precisa ver misturada com o resumo executivo — ver decisão da Etapa 6.
// `summary === null` é o estado de carregamento; blocos individuais `null`
// dentro de um `summary` já carregado mostram mensagem específica (Etapa 1
// estendida para performance/losses nesta etapa).
export function TechnicalPerformanceSection({ summary }: { summary: PhotovoltaicSummaryResponse | null }) {
  if (summary === null) {
    return <MetricCardSkeletonGrid count={4} />
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <PerformanceRatioCard
          performance={summary.performance}
          unavailableReason={summary.performance_unavailable_reason}
        />
        <SpecificYieldCard
          performance={summary.performance}
          unavailableReason={summary.performance_unavailable_reason}
        />
        <ReportingAvailabilityCard
          performance={summary.performance}
          unavailableReason={summary.performance_unavailable_reason}
        />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <BaselineDegradationCard
          baseline={summary.baseline}
          unavailableReason={summary.baseline_unavailable_reason}
          referenceCompleteOn={summary.reference_complete_on}
        />
        <LossBreakdownSection losses={summary.losses} unavailableReason={summary.losses_unavailable_reason} />
      </div>
    </div>
  )
}
