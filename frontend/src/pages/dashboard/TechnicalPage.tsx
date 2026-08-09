import { fetchPhotovoltaicSummary } from '../../lib/api'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import type { PhotovoltaicLossItem, PhotovoltaicSummaryResponse } from '../../lib/dashboard/photovoltaic-contracts'
import { parsePhotovoltaicSummary, ratioToPercent } from '../../lib/dashboard/photovoltaic-contracts'
import type { Severity } from '../../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../../lib/format'
import {
  EVIDENCE_LEVEL_META,
  LOSS_CATEGORY_LABEL,
  performanceSeverity,
  SEVERITY_BG,
  SEVERITY_TEXT,
} from '../../lib/dashboard/visuals'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { RefreshBar } from '../../components/RefreshBar'
import { RetryableError } from '../../components/RetryableError'
import { EmptyState } from '../../components/EmptyState'
import { SectionTitle } from '../../components/SectionTitle'
import { TechnicalPerformanceSection } from '../../components/TechnicalPerformanceSection'

// Usado quando `/photovoltaic/summary` falha (rede ou erro de servidor, não
// 401): a seção mostra as mensagens de indisponibilidade por bloco em vez de
// ficar carregando indefinidamente. Cópia local da mesma função em
// `DashboardPage.tsx` — cada módulo tem sua própria instância de
// `usePlantResource` (ADR-072, Decisão 3: fronteira de fetch por módulo, sem
// estado compartilhado entre módulos), e `DashboardPage.tsx` ainda precisa
// da sua própria cópia para derivar `expectedProduction`, consumido por
// `ProductionHistorySection` até o módulo Produção migrar (Etapa 4).
function fallbackPvSummary(plantId: string): PhotovoltaicSummaryResponse {
  return {
    plant_id: plantId,
    performance: null,
    performance_unavailable_reason: 'NO_PERFORMANCE_RESULTS',
    baseline: null,
    baseline_unavailable_reason: 'NO_PERFORMANCE_HISTORY',
    reference_complete_on: null,
    losses: null,
    losses_unavailable_reason: 'NO_LOSS_ASSESSMENTS',
    expectedProduction: { available: false, reason: 'NO_PERFORMANCE_HISTORY', referenceCompleteOn: null },
  }
}

const SUMMARY_TILE_TONE: Record<Severity | 'brand', { bar: string; bg: string; text: string }> = {
  brand: {
    bar: 'bg-[var(--color-brand-primary)]',
    bg: 'bg-[var(--color-brand-primary-light)]',
    text: 'text-[var(--color-brand-primary)]',
  },
  success: {
    bar: 'bg-[var(--color-success)]',
    bg: SEVERITY_BG.success,
    text: SEVERITY_TEXT.success,
  },
  warning: {
    bar: 'bg-[var(--color-warning)]',
    bg: SEVERITY_BG.warning,
    text: SEVERITY_TEXT.warning,
  },
  danger: {
    bar: 'bg-[var(--color-danger)]',
    bg: SEVERITY_BG.danger,
    text: SEVERITY_TEXT.danger,
  },
  neutral: {
    bar: 'bg-gray-300',
    bg: SEVERITY_BG.neutral,
    text: SEVERITY_TEXT.neutral,
  },
}

interface TechnicalSummaryTileProps {
  label: string
  value: string
  supportingText: string
  tone: Severity | 'brand'
}

function TechnicalSummaryTile({ label, value, supportingText, tone }: TechnicalSummaryTileProps) {
  const meta = SUMMARY_TILE_TONE[tone]

  return (
    <article className="min-h-[7.5rem] rounded-xl border border-gray-200 bg-[var(--color-surface)] p-3.5 shadow-sm sm:min-h-[8.5rem] sm:p-4">
      <div className={`mb-3 h-1 w-10 rounded-full sm:mb-4 ${meta.bar}`} aria-hidden="true" />
      <div className="text-sm font-semibold text-gray-600">{label}</div>
      <div className="mt-2 text-xl font-bold tracking-tight text-gray-950 sm:text-2xl">{value}</div>
      <div className={`mt-3 inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${meta.bg} ${meta.text}`}>
        {supportingText}
      </div>
    </article>
  )
}

function formatPercent(value: number | null, maximumFractionDigits = 0): string {
  return value === null ? '—' : `${formatNumber(value, maximumFractionDigits)}%`
}

function formatDailyKwh(value: number | null): string {
  return value === null ? '—' : `${formatNumber(value)} kWh/dia`
}

function technicalHealthLabel(pr: number | null): string {
  if (pr === null) return 'Aguardando dados'
  const severity = performanceSeverity(pr)
  if (severity === 'success') return 'Saudável'
  if (severity === 'warning') return 'Atenção'
  return 'Crítico'
}

function topLossCandidate(losses: PhotovoltaicLossItem[] | null): PhotovoltaicLossItem | null {
  if (losses === null) return null

  const candidates = losses
    .filter((loss) => loss.evidence_level === 'LIKELY' || loss.evidence_level === 'POSSIBLE')
    .sort((left, right) => {
      const leftEvidence = left.evidence_level === 'LIKELY' ? 0 : 1
      const rightEvidence = right.evidence_level === 'LIKELY' ? 0 : 1
      if (leftEvidence !== rightEvidence) return leftEvidence - rightEvidence
      return (toNumber(right.estimated_loss_percent) ?? -1) - (toNumber(left.estimated_loss_percent) ?? -1)
    })

  return candidates[0] ?? null
}

// Módulo Técnico (ADR-072, Etapa 2) — o menor dos 4, um único recurso
// (`/photovoltaic/summary`, ver ADR seção 2). Sem o toggle expandir/colapsar
// que `TechnicalPerformanceSection` tinha antes desta etapa: a rota já é a
// divulgação progressiva.
export function TechnicalPage() {
  const { plantId, plants, loading: plantsLoading, error: plantsError } = usePlant()
  // `document.title`/foco por rota (ADR-072, Etapa 6) — ver `useModuleTitle`.
  // Chamado antes de qualquer `return` condicional abaixo (regra dos hooks).
  const headingRef = useModuleTitle('Técnico')

  const pvSummaryResource = usePlantResource({
    plantId,
    fetcher: fetchPhotovoltaicSummary,
    parse: parsePhotovoltaicSummary,
    errorMessage: 'Erro ao buscar resumo fotovoltaico.',
  })

  // Enquanto a lista de usinas (`PlantContext`) ainda carrega, nenhuma
  // requisição deste módulo foi disparada — mesmo esqueleto de carregamento
  // usado por `DashboardPage` para o mesmo estado.
  if (plantsLoading) {
    return <MetricCardSkeletonGrid />
  }

  // Falha ao carregar `/plants`: sem usina resolvida, não há como buscar
  // `/photovoltaic/summary`.
  if (plantsError) {
    return (
      <RetryableError
        message={plantsError}
        onRetry={() => window.location.reload()}
        className="mb-6"
      />
    )
  }

  // Organização sem nenhuma usina cadastrada (`count == 0`, ADR-069, seção 7):
  // estado vazio explícito, zero chamadas de dados disparadas.
  if (!plantId || plants.length === 0) {
    return (
      <EmptyState
        eyebrow="Configuração inicial"
        title="Nenhuma usina cadastrada"
        description="Nenhuma usina cadastrada para esta conta ainda. Quando uma usina for vinculada, PR, perdas, degradação e disponibilidade aparecerão aqui."
        tone="brand"
      />
    )
  }

  // A partir daqui `plantId` está estreitado para `string` pelas guardas
  // acima. Cai no fallback só quando `pvSummaryResource.status === 'error'`
  // — enquanto `'loading'` (inclusive num refetch da MESMA usina, que
  // preserva o `data` anterior em vez de zerar), `pvSummary` reflete o
  // `data` já resolvido ou `null` enquanto a primeira resposta ainda não
  // chegou, nunca o fallback prematuramente (mesmo comportamento de
  // `DashboardPage`).
  const pvSummary = pvSummaryResource.status === 'error' ? fallbackPvSummary(plantId) : pvSummaryResource.data
  const loading = pvSummaryResource.status === 'loading'
  const performanceRatio = ratioToPercent(pvSummary?.performance?.performance_ratio ?? null)
  const correctedPerformanceRatio = ratioToPercent(
    pvSummary?.performance?.temperature_corrected_performance_ratio ?? null
  )
  const reportingAvailability = ratioToPercent(pvSummary?.performance?.reporting_availability_ratio ?? null)
  const expectedDailyProduction = pvSummary?.expectedProduction.available
    ? pvSummary.expectedProduction.kwh
    : null
  const healthTone: Severity = performanceRatio === null ? 'neutral' : performanceSeverity(performanceRatio)
  const availabilityTone: Severity =
    reportingAvailability === null ? 'neutral' : performanceSeverity(reportingAvailability)
  const leadingLoss = topLossCandidate(pvSummary?.losses ?? null)
  const leadingLossTone: Severity = leadingLoss ? EVIDENCE_LEVEL_META[leadingLoss.evidence_level].severity : 'success'
  const leadingLossValue = leadingLoss ? toNumber(leadingLoss.estimated_loss_percent) : null

  return (
    <>
      <div className="mb-6 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--color-brand-primary)]">
            Diagnóstico técnico
          </p>
          {/* `<h1>` próprio do módulo (ADR-072, Etapa 6) — ver o mesmo comentário
              em `OverviewPage.tsx`. */}
          <h1 ref={headingRef} tabIndex={-1} className="mt-2 text-2xl font-bold tracking-tight text-gray-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] rounded sm:text-3xl">
            Técnico
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-600">
            Entenda se a usina está performando bem, se os dados são confiáveis e qual causa técnica merece investigação primeiro.
          </p>
        </div>
        <RefreshBar onRefresh={pvSummaryResource.refetch} loading={loading} className="mb-0 lg:justify-self-end" />
      </div>

      <section className="mb-6">
        <SectionTitle as="h2">Resumo técnico</SectionTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <TechnicalSummaryTile
            label="Saúde técnica"
            value={technicalHealthLabel(performanceRatio)}
            supportingText={`PR bruto ${formatPercent(performanceRatio)}`}
            tone={healthTone}
          />
          <TechnicalSummaryTile
            label="Disponibilidade dos dados"
            value={formatPercent(reportingAvailability)}
            supportingText="reporte dos devices"
            tone={availabilityTone}
          />
          <TechnicalSummaryTile
            label="Principal suspeita"
            value={leadingLoss ? LOSS_CATEGORY_LABEL[leadingLoss.category] : 'Sem causa crítica'}
            supportingText={
              leadingLoss
                ? `${EVIDENCE_LEVEL_META[leadingLoss.evidence_level].label} · ${formatPercent(leadingLossValue, 1)}`
                : loading
                  ? 'Carregando perdas'
                  : 'sem evidência relevante'
            }
            tone={leadingLossTone}
          />
          <TechnicalSummaryTile
            label="Produção esperada"
            value={formatDailyKwh(expectedDailyProduction)}
            supportingText={
              expectedDailyProduction === null
                ? loading
                  ? 'Carregando baseline'
                  : 'baseline indisponível'
                : correctedPerformanceRatio === null
                  ? 'baseline sazonal'
                  : `PR corrigido ${formatPercent(correctedPerformanceRatio)}`
            }
            tone="brand"
          />
        </div>
      </section>

      <TechnicalPerformanceSection summary={pvSummary} />
    </>
  )
}
