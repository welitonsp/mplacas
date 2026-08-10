import { fetchAnomalyHistory, fetchMonthlyProductionHistory, fetchPhotovoltaicSummary } from '../../lib/api'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import type { AnomalyDashboardResponse, AnomalyFetchError, AnomalyFetchState, Severity } from '../../lib/dashboard/contracts'
import { classifyAnomalyErrorStatus, latestNonNullProductionDate, parseAnomalyDashboard } from '../../lib/dashboard/contracts'
import { parseMonthlyProductionHistory } from '../../lib/dashboard/monthly-history-contracts'
import type { PhotovoltaicSummaryResponse } from '../../lib/dashboard/photovoltaic-contracts'
import { parsePhotovoltaicSummary } from '../../lib/dashboard/photovoltaic-contracts'
import { formatFullDate, formatNumber, toNumber } from '../../lib/format'
import { levelLabel, levelSeverity } from '../../lib/dashboard/visuals'
import { SectionTitle } from '../../components/SectionTitle'
import { LatestDailyProductionCard } from '../../components/LatestDailyProductionCard'
import { EmptyState } from '../../components/EmptyState'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { MonthlyProductionSection } from '../../components/MonthlyProductionSection'
import { ProductionHistorySection } from '../../components/ProductionHistorySection'
import { RefreshBar } from '../../components/RefreshBar'
import { RetryableError } from '../../components/RetryableError'
import { PageHeader } from '../../components/PageHeader'
import { SummaryTile } from '../../components/SummaryTile'
import { ProductionDiagnosticPanel } from '../../components/ProductionDiagnosticPanel'

// Usado quando `/photovoltaic/summary` falha (rede ou erro de servidor, não
// 401): garante um `expectedProduction.available: false` explícito para
// `ProductionHistorySection` em vez de deixar a seção carregando
// indefinidamente. Cópia local da mesma função em `DashboardPage.tsx`/
// `TechnicalPage.tsx` — cada módulo tem sua própria instância de
// `usePlantResource` (ADR-072, Decisão 3: fronteira de fetch por módulo, sem
// estado compartilhado entre módulos). Aqui, diferente do Técnico, só
// `expectedProduction` é consumido — o restante do resumo (performance/
// baseline/losses) pertence ao módulo Técnico.
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

function formatKwh(value: number | null): string {
  return value === null ? '—' : `${formatNumber(value)} kWh`
}

function formatDeviation(value: number | null): string {
  if (value === null) return '—'
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${formatNumber(value, 1)}%`
}

// Módulo Produção (ADR-072, Etapa 4) — três recursos (ver ADR seção 2):
// `anomalies` (`/energy/anomalies/latest`), `pvSummary`
// (`/photovoltaic/summary`, usado só para `expectedProduction`) e
// `monthlyHistory` (`/reports/monthly/history`). Renderiza
// `MonthlyProductionSection` + `ProductionHistorySection` +
// `LatestDailyProductionCard`, na mesma composição/ordem que tinham em
// `DashboardPage.tsx` antes desta etapa.
export function ProductionPage() {
  const { plantId, plants, loading: plantsLoading, error: plantsError } = usePlant()
  // `document.title`/foco por rota (ADR-072, Etapa 6) — ver `useModuleTitle`.
  // Chamado antes de qualquer `return` condicional abaixo (regra dos hooks).
  const headingRef = useModuleTitle('Produção')

  // `null` (`.data`) = ainda carregando `/energy/anomalies/latest`. Contrato
  // 200 sempre (campos por dia `null` sem expectativa) — este recurso NÃO
  // depende de `pvSummaryResource` abaixo: é buscado assim que há `plantId`,
  // independente do baseline sazonal já existir (ver usina com produção real
  // mas sem baseline — o card de histórico não pode ficar preso esperando um
  // dado que talvez nunca chegue). `classifyError` reusa
  // `classifyAnomalyErrorStatus` (já testado isoladamente em
  // `contracts.test.ts`): 404 vira `'NOT_FOUND'`, 5xx vira `'SERVER_ERROR'`, e
  // 401 já volta `null` de dentro da própria função — falha silenciosa, mesma
  // política de antes (`apiFetch` já tentou refresh; se falhou, o usuário
  // está sendo deslogado, não há nada a comunicar aqui). Falha de rede/
  // contrato (`kind !== 'http'`) cai no mesmo `'SERVER_ERROR'`, mesma
  // categoria de "algo quebrou" que um 5xx no comportamento anterior.
  const anomalies = usePlantResource<AnomalyDashboardResponse, AnomalyFetchError>({
    plantId,
    fetcher: fetchAnomalyHistory,
    parse: parseAnomalyDashboard,
    classifyError: (failure) =>
      failure.kind === 'http' ? classifyAnomalyErrorStatus(failure.status) : 'SERVER_ERROR',
  })
  // Adapta o resultado de `usePlantResource` de volta ao shape
  // `AnomalyFetchState` que `ProductionHistorySection`/
  // `LatestDailyProductionCard` já esperam — o contrato de prop desses dois
  // componentes (e seus testes) não muda nesta etapa.
  const anomalyState: AnomalyFetchState = {
    data: anomalies.data,
    loading: anomalies.status === 'loading',
    error: anomalies.error,
  }
  // `null` (`.data`) = ainda carregando `/photovoltaic/summary`. `errorMessage`
  // aqui só alimenta o `console.error` do hook: esta seção nunca expõe o erro
  // na tela — em caso de falha, a derivação de `pvSummary`/`expectedProduction`
  // logo abaixo das guardas de render cai em `fallbackPvSummary`, que já traz
  // um motivo de indisponibilidade explícito.
  const pvSummaryResource = usePlantResource({
    plantId,
    fetcher: fetchPhotovoltaicSummary,
    parse: parsePhotovoltaicSummary,
    errorMessage: 'Erro ao buscar resumo fotovoltaico.',
  })
  // `null` (`.data`) = ainda carregando `/reports/monthly/history` (histórico
  // de produção por ciclo de faturamento). `fetcher` precisa de um wrapper
  // porque `fetchMonthlyProductionHistory` recebe `limit` como segundo
  // parâmetro, que a assinatura de `usePlantResource.fetcher` não conhece.
  const monthlyHistory = usePlantResource({
    plantId,
    fetcher: (id: string) => fetchMonthlyProductionHistory(id, 12),
    parse: parseMonthlyProductionHistory,
    errorMessage: 'Erro ao buscar histórico de produção.',
  })

  // Refetch único para os 3 recursos deste módulo — usado pelo botão
  // "Atualizar" (`RefreshBar`). Erros de cada recurso continuam isolados por
  // seção (ver `monthlyHistory.error`/`RetryableError` de anomalias abaixo) —
  // este botão só força uma nova tentativa dos 3 ao mesmo tempo.
  const refreshAll = () => {
    anomalies.refetch()
    pvSummaryResource.refetch()
    monthlyHistory.refetch()
  }
  // Combinado dos 3 recursos — usado pelo `disabled`/texto "Atualizando..."
  // do `RefreshBar`.
  const loading =
    anomalies.status === 'loading' ||
    pvSummaryResource.status === 'loading' ||
    monthlyHistory.status === 'loading'

  // Enquanto a lista de usinas (`PlantContext`) ainda carrega, nenhuma
  // requisição deste módulo foi disparada — mesmo esqueleto de carregamento
  // usado por `DashboardPage`/`FinancialPage`/`TechnicalPage` para o mesmo
  // estado.
  if (plantsLoading) {
    return <MetricCardSkeletonGrid />
  }

  // Falha ao carregar `/plants`: sem usina resolvida, não há como buscar dado
  // nenhum deste módulo.
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
        description="Nenhuma usina cadastrada para esta conta ainda. Quando uma usina for vinculada, histórico, desvios e produção esperada aparecerão aqui."
        tone="brand"
      />
    )
  }

  // A partir daqui `plantId` está estreitado para `string` pelas guardas
  // acima. Cai no fallback só quando `pvSummaryResource.status === 'error'`:
  // enquanto `'loading'` (inclusive num refetch da MESMA usina, que preserva
  // o `data` anterior em vez de zerar — ver `usePlantResource`), `pvSummary`
  // reflete o `data` já resolvido ou `null` enquanto a primeira resposta
  // ainda não chegou, nunca o fallback prematuramente.
  const pvSummary = pvSummaryResource.status === 'error' ? fallbackPvSummary(plantId) : pvSummaryResource.data
  const expectedProduction = pvSummary?.expectedProduction ?? null
  const latestProductionDate = anomalies.data ? latestNonNullProductionDate(anomalies.data.daily) : null
  const latestProductionPoint =
    latestProductionDate && anomalies.data
      ? anomalies.data.daily.find((point) => point.date === latestProductionDate) ?? null
      : null
  const latestActualProduction = latestProductionPoint ? toNumber(latestProductionPoint.actual_production_kwh) : null
  const latestExpectedProduction = latestProductionPoint ? toNumber(latestProductionPoint.expected_production_kwh) : null
  const latestDeviation = latestProductionPoint ? toNumber(latestProductionPoint.deviation_percent) : null
  const latestLevel = latestProductionPoint?.level ?? null
  const deviationTone = latestProductionPoint ? levelSeverity(latestLevel) : 'neutral'
  const streakDays = anomalies.data?.current_streak_days ?? null
  const streakTone: Severity = streakDays === null ? 'neutral' : streakDays > 0 ? 'warning' : 'success'

  return (
    <>
      <PageHeader
        eyebrow="Painel de produção"
        title="Produção"
        description="Acompanhe ciclos fechados, geração diária e desvios contra o esperado para priorizar a investigação certa."
        headingRef={headingRef}
        insights={[
          { label: 'Pergunta', value: 'A geração caiu ou normalizou?' },
          { label: 'Leitura', value: 'Ciclo, dia e desvio' },
          { label: 'Saída', value: 'Ação operacional' },
        ]}
        actions={<RefreshBar onRefresh={refreshAll} loading={loading} className="mb-0 lg:justify-self-end" />}
      />
      <section className="mb-6">
        <SectionTitle as="h2">Resumo operacional</SectionTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryTile
            label="Última produção"
            value={formatKwh(latestActualProduction)}
            supportingText={
              anomalyState.loading && !latestProductionPoint
                ? 'Carregando histórico'
                : latestProductionDate
                  ? `Dado de ${formatFullDate(latestProductionDate)}`
                  : 'Sem dado diário'
            }
            tone="brand"
          />
          <SummaryTile
            label="Esperado no dia"
            value={formatKwh(latestExpectedProduction)}
            supportingText={latestExpectedProduction === null ? 'Baseline indisponível' : 'Referência diária'}
            tone="neutral"
          />
          <SummaryTile
            label="Desvio"
            value={formatDeviation(latestDeviation)}
            supportingText={latestProductionPoint ? levelLabel(latestLevel) : 'Sem comparação'}
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

      <div className="grid grid-cols-1 gap-4 md:grid-cols-6 lg:grid-cols-12 lg:gap-6 items-start">
        {/* Produção por ciclo de faturamento (12 ciclos fechados) — leitura do
            grosso pro fino: o resumo mensal primeiro, o histórico diário de 90
            dias (bloco seguinte) depois. Erro desta seção é isolado
            (`monthlyHistory.error`) e não trava o resto do módulo se a chamada
            falhar. */}
        <section className="md:col-span-6 lg:col-span-12">
          <SectionTitle as="h2">Produção por ciclo de faturamento</SectionTitle>
          {monthlyHistory.error ? (
            <RetryableError
              message={monthlyHistory.error}
              onRetry={monthlyHistory.refetch}
            />
          ) : (
            <MonthlyProductionSection history={monthlyHistory.data} />
          )}
        </section>

        {/* Histórico de produção diária — bloco maior (gráfico), ao lado da
            produção real vs. esperada. */}
        <section className="md:col-span-4 lg:col-span-8 2xl:col-span-9">
          <SectionTitle as="h2">Histórico de produção</SectionTitle>
          <ProductionHistorySection
            anomalyState={anomalyState}
            expectedProduction={expectedProduction}
            onRetry={anomalies.refetch}
          />
        </section>

        <section className="md:col-span-2 lg:col-span-4 2xl:col-span-3">
          <SectionTitle as="h2">Produção do último dia vs. esperada</SectionTitle>
          {/* Compara o último dia com dado diário coletado (real vs. esperado,
              mesma escala kWh/dia) — não o total do ciclo (~30 dias) contra uma
              média diária. A produção do ciclo continua visível no nó
              "Produção" de `EnergyFlowDiagram`, na Visão Geral. */}
          <LatestDailyProductionCard anomalyState={anomalyState} className="h-full" />
        </section>
      </div>
    </>
  )
}
