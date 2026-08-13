import { fetchDeviceDailyStatus, fetchPhotovoltaicSummary } from '../../lib/api'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import { parseDeviceDailyStatus } from '../../lib/dashboard/device-contracts'
import type { PhotovoltaicLossItem, PhotovoltaicSummaryResponse } from '../../lib/dashboard/photovoltaic-contracts'
import { parsePhotovoltaicSummary, ratioToPercent } from '../../lib/dashboard/photovoltaic-contracts'
import type { Severity } from '../../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../../lib/format'
import {
  EVIDENCE_LEVEL_META,
  LOSS_CATEGORY_LABEL,
  performanceSeverity,
} from '../../lib/dashboard/visuals'
import { DeviceStatusSection } from '../../components/DeviceStatusSection'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { RefreshBar } from '../../components/RefreshBar'
import { RetryableError } from '../../components/RetryableError'
import { EmptyState } from '../../components/EmptyState'
import { SectionTitle } from '../../components/SectionTitle'
import { TechnicalPerformanceSection } from '../../components/TechnicalPerformanceSection'
import { PageHeader } from '../../components/PageHeader'
import { SummaryTile } from '../../components/SummaryTile'
import { TechnicalDiagnosticPanel } from '../../components/TechnicalDiagnosticPanel'

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

// Módulo Técnico (ADR-072, Etapa 2) — originalmente o menor dos 4, com um
// único recurso (`/photovoltaic/summary`, ver ADR seção 2). ADR-074, Decisão
// 5 acrescenta um segundo recurso (`/devices/daily-status`, estado por
// inversor) — 2 requisições ao entrar no módulo, custo aceito no próprio ADR.
// Sem o toggle expandir/colapsar que `TechnicalPerformanceSection` tinha
// antes desta etapa: a rota já é a divulgação progressiva.
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

  // Segundo recurso do módulo (ADR-074, Decisão 5): estado por inversor —
  // drill-down do agregado "Disponibilidade dos dados" acima. Fronteira de
  // fetch própria (ADR-072, Decisão 3), isolada de `pvSummaryResource`: uma
  // falha de `/devices/daily-status` nunca apaga PR/perdas/degradação, e
  // vice-versa. O módulo passa de 1 para 2 requisições ao entrar — custo
  // aceito no ADR (o mais barato do painel hoje, §1.4 do plano de auditoria).
  const deviceStatusResource = usePlantResource({
    plantId,
    fetcher: fetchDeviceDailyStatus,
    parse: parseDeviceDailyStatus,
    errorMessage: 'Erro ao buscar status dos inversores.',
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
  // Refetch único para os 2 recursos deste módulo, mesmo padrão de
  // `refreshAll` em `FinancialPage.tsx` — o botão "Atualizar" força uma nova
  // tentativa dos dois ao mesmo tempo; cada recurso mantém seu próprio
  // estado de erro/retry independente.
  const refreshAll = () => {
    pvSummaryResource.refetch()
    deviceStatusResource.refetch()
  }
  const anyLoading = loading || deviceStatusResource.status === 'loading'
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
      <PageHeader
        eyebrow="Diagnóstico técnico"
        title="Técnico"
        description="Entenda se a usina está performando bem, se os dados são confiáveis e qual causa técnica merece investigação primeiro."
        headingRef={headingRef}
        insights={[
          { label: 'Pergunta', value: 'Qual causa atacar primeiro?' },
          { label: 'Leitura', value: 'PR, perdas e disponibilidade' },
          { label: 'Saída', value: 'Plano de investigação' },
        ]}
        actions={<RefreshBar onRefresh={refreshAll} loading={anyLoading} className="mb-0 lg:justify-self-end" />}
      />
      <section className="mb-6">
        <SectionTitle as="h2">Resumo técnico</SectionTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryTile
            label="Saúde técnica"
            value={technicalHealthLabel(performanceRatio)}
            supportingText={`PR bruto ${formatPercent(performanceRatio)}`}
            tone={healthTone}
          />
          <SummaryTile
            label="Disponibilidade dos dados"
            value={formatPercent(reportingAvailability)}
            supportingText="reporte dos devices"
            tone={availabilityTone}
          />
          <SummaryTile
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
          <SummaryTile
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

      <section className="mb-6">
        <TechnicalDiagnosticPanel summary={pvSummary} />
      </section>

      {/* Visão por inversor (ADR-074, Decisão 5) — entre o diagnóstico de
          causa e o desempenho técnico agregado: drill-down direto do tile
          "Disponibilidade dos dados" acima, resposta ao lado da pergunta. */}
      <section className="mb-6">
        <DeviceStatusSection resource={deviceStatusResource} />
      </section>

      <TechnicalPerformanceSection summary={pvSummary} />
    </>
  )
}
