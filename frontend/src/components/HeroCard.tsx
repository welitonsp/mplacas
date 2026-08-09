import type { Diagnostic, MetricValue } from '../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../lib/format'
import { SEVERITY_BG, SEVERITY_DOT, SEVERITY_TEXT, statusMeta } from '../lib/dashboard/visuals'
import { AttentionSummary } from './AttentionSummary'
import { Card } from './Card'
import { DataFreshness } from './DataFreshness'
import { Gauge } from './charts/Gauge'

// Abaixo de `lg` o layout é o empilhamento vertical original (ciclo+headline,
// badge de status ao lado em `sm+`, saúde da usina embaixo). A partir de `lg`
// (bloco ocupando a largura toda do grid de página — ver `DashboardPage`), vira
// uma faixa horizontal de três colunas: headline | saúde da usina | status —
// usando `grid-template-areas` para reposicionar visualmente sem duplicar
// marcação nem depender da ordem no DOM.
const AREAS_BASE = "[grid-template-areas:'headline'_'badge'_'score'_'freshness']"
const AREAS_SM = "sm:[grid-template-areas:'headline_badge'_'score_score'_'freshness_freshness']"
const AREAS_LG = "lg:[grid-template-areas:'headline_score_badge'_'headline_score_freshness']"

export function HeroCard({
  referenceMonth,
  headline,
  status,
  healthScore,
  latestDataDate = null,
  lastSyncedAt = null,
  diagnostics = [],
}: {
  referenceMonth: string
  headline: string
  status: string
  healthScore: MetricValue
  latestDataDate?: string | null
  lastSyncedAt?: Date | null
  // Ver `AttentionSummary` — chip "N críticos" só aparece quando há pelo
  // menos um diagnóstico CRITICAL; lista vazia (padrão) não renderiza nada.
  diagnostics?: Diagnostic[]
}) {
  const meta = statusMeta(status)
  const score = toNumber(healthScore)

  return (
    <Card accent={meta.severity} className="sm:p-6">
      <div
        className={`grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:gap-x-4 lg:grid-cols-[minmax(0,1fr)_auto_auto] lg:items-center lg:gap-x-8 lg:gap-y-1 ${AREAS_BASE} ${AREAS_SM} ${AREAS_LG}`}
      >
        <div className="[grid-area:headline]">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Ciclo de referência: {referenceMonth}
          </p>
          <p className="mt-1 text-3xl font-semibold text-gray-900">{headline}</p>
          <AttentionSummary diagnostics={diagnostics} />
        </div>

        {score != null && (
          <div className="mt-5 flex flex-col items-center [grid-area:score] sm:mt-5 lg:mt-0 lg:w-64 lg:max-w-xs">
            <Gauge
              value={score}
              label="Saúde da usina"
              valueLabel={`${formatNumber(score, 0)}/100`}
              tone={meta.severity}
              size={112}
            />
          </div>
        )}

        <span
          className={`mt-3 inline-flex shrink-0 items-center gap-1.5 self-start rounded-full px-3 py-1 text-xs font-semibold [grid-area:badge] justify-self-start sm:mt-0 sm:justify-self-end lg:justify-self-end ${SEVERITY_BG[meta.severity]} ${SEVERITY_TEXT[meta.severity]}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${SEVERITY_DOT[meta.severity]}`} />
          {meta.label}
        </span>

        <div className="mt-2 [grid-area:freshness] justify-self-start sm:justify-self-end lg:justify-self-end">
          <DataFreshness latestDataDate={latestDataDate} lastSyncedAt={lastSyncedAt} />
        </div>
      </div>
    </Card>
  )
}
