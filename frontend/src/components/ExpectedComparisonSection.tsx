import type { AnomalyFetchState, Severity } from '../lib/dashboard/contracts'
import { latestNonNullProductionDate } from '../lib/dashboard/contracts'
import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'
import { formatNumber, toNumber } from '../lib/format'
import { levelLabel, levelSeverity } from '../lib/dashboard/visuals'
import { SectionTitle } from './SectionTitle'
import { SummaryTile } from './SummaryTile'
import { LatestDailyProductionCard } from './LatestDailyProductionCard'
import { ProductionDiagnosticPanel } from './ProductionDiagnosticPanel'
import { EpisodeTimelineSection } from './EpisodeTimelineSection'

function formatDeviation(value: number | null): string {
  if (value === null) return '—'
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${formatNumber(value, 1)}%`
}

// Tudo o que só existe contra a produção esperada (ADR-083, etapa 3): régua do
// último dia, desvio, sequência de atenção, diagnóstico do período e episódios.
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
  const data = anomalyState.data
  const latestDate = data ? latestNonNullProductionDate(data.daily) : null
  const latestPoint = latestDate && data ? (data.daily.find((point) => point.date === latestDate) ?? null) : null
  const latestDeviation = latestPoint ? toNumber(latestPoint.deviation_percent) : null
  const latestLevel = latestPoint?.level ?? null
  const deviationTone: Severity = latestPoint ? levelSeverity(latestLevel) : 'neutral'
  const streakDays = data?.current_streak_days ?? null
  const streakTone: Severity = streakDays === null ? 'neutral' : streakDays > 0 ? 'warning' : 'success'

  return (
    <>
      <section className="mb-6">
        <SectionTitle as="h2">Último dia contra o esperado</SectionTitle>
        <div className="grid grid-flow-row-dense grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3">
          <LatestDailyProductionCard anomalyState={anomalyState} className="col-span-2 h-full" />
          <SummaryTile
            label="Desvio"
            value={formatDeviation(latestDeviation)}
            supportingText={latestPoint ? levelLabel(latestLevel) : 'Sem comparação'}
            tone={deviationTone}
          />
          <SummaryTile
            label="Sequência de atenção"
            value={streakDays === null ? '—' : `${formatNumber(streakDays, 0)} ${streakDays === 1 ? 'dia' : 'dias'}`}
            supportingText={streakDays === null ? 'Aguardando dados' : streakDays > 0 ? 'abaixo do esperado' : 'sem alerta ativo'}
            tone={streakTone}
          />
        </div>
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
