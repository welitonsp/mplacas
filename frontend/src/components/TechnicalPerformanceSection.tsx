import type { PhotovoltaicSummaryResponse } from '../lib/dashboard/photovoltaic-contracts'
import { BaselineDegradationCard } from './BaselineDegradationCard'
import { LossBreakdownSection } from './LossBreakdownSection'
import { MetricCardSkeletonGrid } from './MetricCardSkeletonGrid'
import { PerformanceRatioCard } from './PerformanceRatioCard'
import { ReportingAvailabilityCard } from './ReportingAvailabilityCard'
import { SectionTitle } from './SectionTitle'
import { SpecificYieldCard } from './SpecificYieldCard'

// Bloco próprio ("Como está o desempenho técnico?"): PR, PR corrigido por
// temperatura, yield específico, disponibilidade de reporte, degradação
// anualizada e atribuição de causa de perda. `summary === null` é o estado de
// carregamento; blocos individuais `null` dentro de um `summary` já
// carregado mostram mensagem específica.
//
// ADR-072 (Etapa 2): o toggle expandir/colapsar que esta seção teve (chave de
// `localStorage` `mplacas:technical-performance-expanded`) foi removido — a
// seção agora vive isolada na rota `/dashboard/tecnico`
// (`pages/dashboard/TechnicalPage.tsx`), que o usuário escolhe entrar
// deliberadamente; a navegação em si já é a divulgação progressiva que o
// toggle existia para fornecer dentro de uma página longa com 10 seções
// empilhadas.
export function TechnicalPerformanceSection({ summary }: { summary: PhotovoltaicSummaryResponse | null }) {
  return (
    <div>
      <SectionTitle as="h2">Desempenho técnico</SectionTitle>

      <div role="region" aria-label="Desempenho técnico">
        {summary === null ? (
          <MetricCardSkeletonGrid count={4} />
        ) : (
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
        )}
      </div>
    </div>
  )
}
