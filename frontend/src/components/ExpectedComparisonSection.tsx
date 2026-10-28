import type { AnomalyFetchState } from '../lib/dashboard/contracts'
import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'
import { SectionTitle } from './SectionTitle'
import { LatestDailyProductionCard } from './LatestDailyProductionCard'
import { ProductionDiagnosticPanel } from './ProductionDiagnosticPanel'
import { EpisodeTimelineSection } from './EpisodeTimelineSection'

// Tudo o que só existe contra a produção esperada (ADR-083, etapa 3): régua do
// último dia, diagnóstico do período e episódios.
// Chunk próprio (carregado sob demanda pela aba Energia): no primeiro ano da
// usina, sem referência, nada disto aparece — e nada disto é baixado.
export function ExpectedComparisonSection({
  anomalyState,
  expectedProduction,
  onRetry,
}: {
  anomalyState: AnomalyFetchState
  expectedProduction: ExpectedDailyProduction | null
  onRetry: () => void
}) {
  return (
    <>
      {/* Só a régua do último dia. Os cartões "Desvio" e "Sequência de
          atenção" saíram: o desvio já está na régua (valor do backend) e a
          sequência já aparece no aviso do gráfico e no diagnóstico abaixo
          (ADR-077, decisão 15 — cada número uma vez por tela). */}
      <section className="mb-6">
        <SectionTitle as="h2">Último dia contra o esperado</SectionTitle>
        <LatestDailyProductionCard anomalyState={anomalyState} />
      </section>

      <section className="mb-6" aria-label="Diagnóstico de produção do período">
        <ProductionDiagnosticPanel anomalyState={anomalyState} expectedProduction={expectedProduction} />
      </section>

      {/* Episódios (ADR-075): quando um desvio começou e quanto durou. */}
      <section className="mb-6" aria-label="Episódios de produção">
        <EpisodeTimelineSection anomalyState={anomalyState} expectedProduction={expectedProduction} onRetry={onRetry} />
      </section>
    </>
  )
}
