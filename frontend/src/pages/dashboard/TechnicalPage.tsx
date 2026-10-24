import { fetchDeviceDailyStatus, fetchPhotovoltaicSummary } from '../../lib/api'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import { DASHBOARD_PRODUCTION_PATH } from '../../routes'
import { parseDeviceDailyStatus } from '../../lib/dashboard/device-contracts'
import type { PhotovoltaicLossItem, PhotovoltaicSummaryResponse } from '../../lib/dashboard/photovoltaic-contracts'
import { parsePhotovoltaicSummary, ratioToPercent } from '../../lib/dashboard/photovoltaic-contracts'
import type { Severity } from '../../lib/dashboard/contracts'
import { formatFullDate, formatNumber, toNumber } from '../../lib/format'
import {
  LOSS_CATEGORY_LABEL,
  performanceSeverity,
  lossEvidenceMeta,
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

// Principal perda a verificar: com evidência, preferindo LIKELY e, dentro do
// mesmo nível, o maior percentual — por isso o rótulo não diz "maior". O calor
// é física (toda placa rende menos quente) e só aparece quando não há outra
// com evidência, com tom neutro. Comunicação nunca entra: o próprio motor diz
// que é capacidade sem dados, não perda de energia (ADR-083, etapa 3).
function topLossCandidate(losses: PhotovoltaicLossItem[] | null): PhotovoltaicLossItem | null {
  if (losses === null) return null

  const withEvidence = losses.filter(
    (loss) => loss.category !== 'COMMUNICATION' && (loss.evidence_level === 'LIKELY' || loss.evidence_level === 'POSSIBLE'),
  )
  const actionable = withEvidence.filter((loss) => loss.category !== 'TEMPERATURE')
  const candidates = (actionable.length > 0 ? actionable : withEvidence)
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
  const headingRef = useModuleTitle('Detalhes técnicos')

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
  const expectedDailyProduction = pvSummary?.expectedProduction.available
    ? pvSummary.expectedProduction.kwh
    : null
  // Saúde pela performance CORRIGIDA pelo calor quando existe: o PR bruto de um
  // dia quente cai sem que nada esteja errado (ex.: 80% bruto, 86% corrigido),
  // e chamar isso de "Atenção" era alarme sem motivo (ADR-083, etapa 3). Os
  // números de PR ficam só em "Desempenho técnico", abaixo (cada número uma vez).
  const healthRatio = correctedPerformanceRatio ?? performanceRatio
  const healthTone: Severity = healthRatio === null ? 'neutral' : performanceSeverity(healthRatio)
  const leadingLoss = topLossCandidate(pvSummary?.losses ?? null)
  const leadingLossMeta = leadingLoss ? lossEvidenceMeta(leadingLoss.category, leadingLoss.evidence_level) : null
  const leadingLossTone: Severity = leadingLossMeta?.severity ?? 'success'
  const leadingLossValue = leadingLoss ? toNumber(leadingLoss.estimated_loss_percent) : null
  const expectedPending =
    pvSummary && !pvSummary.expectedProduction.available ? pvSummary.expectedProduction.referenceCompleteOn : null

  return (
    <>
      <PageHeader
        eyebrow="Energia"
        title="Detalhes técnicos"
        description="Performance, perdas e inversores, para quem quer ir a fundo."
        backLink={{ to: DASHBOARD_PRODUCTION_PATH, label: 'Voltar para Energia' }}
        headingRef={headingRef}
        actions={<RefreshBar onRefresh={refreshAll} loading={anyLoading} className="mb-0 lg:justify-self-end" />}
      />
      <section className="mb-6">
        <SectionTitle as="h2">Resumo técnico</SectionTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
          <SummaryTile
            label="Saúde técnica"
            value={technicalHealthLabel(healthRatio)}
            supportingText={
              correctedPerformanceRatio !== null
                ? 'Pela performance já descontado o calor'
                : performanceRatio !== null
                  ? 'Pela performance do dia'
                  : 'Aguardando dados'
            }
            tone={healthTone}
          />
          <SummaryTile
            label="Principal perda a verificar"
            value={leadingLoss ? LOSS_CATEGORY_LABEL[leadingLoss.category] : 'Nenhuma relevante'}
            supportingText={
              leadingLoss && leadingLossMeta
                ? `${leadingLossMeta.label} · ${formatPercent(leadingLossValue, 1)}`
                : loading
                  ? 'Carregando perdas'
                  : 'Sem evidência de perda'
            }
            tone={leadingLossTone}
          />
          <SummaryTile
            label="Produção esperada"
            value={expectedDailyProduction !== null ? formatDailyKwh(expectedDailyProduction) : loading ? '…' : 'Em formação'}
            supportingText={
              expectedDailyProduction !== null
                ? 'Referência do dia, pela própria usina'
                : expectedPending
                  ? `Começa em ${formatFullDate(expectedPending)}`
                  : loading
                    ? 'Carregando referência'
                    : 'Ainda sem referência'
            }
            tone="brand"
          />
        </div>
      </section>

      {/* Visão por inversor (ADR-074, Decisão 5). O painel genérico de
          "Diagnóstico de causa" (confiança, "Agir hoje", plano de 3 passos)
          saiu (ADR-083): as causas, com evidência, estão em "Por que produzi
          menos", dentro de "Desempenho técnico". */}
      <section className="mb-6">
        <DeviceStatusSection resource={deviceStatusResource} />
      </section>

      <TechnicalPerformanceSection summary={pvSummary} />
    </>
  )
}
