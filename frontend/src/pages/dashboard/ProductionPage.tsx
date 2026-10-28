import { lazy, Suspense } from 'react'
import { Link } from 'react-router'
import { fetchAnomalyHistory, fetchExecutiveDashboard, fetchMonthlyProductionHistory, fetchPhotovoltaicSummary } from '../../lib/api'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import type { AnomalyDashboardResponse, AnomalyFetchError, AnomalyFetchState } from '../../lib/dashboard/contracts'
import {
  classifyAnomalyErrorStatus,
  parseAnomalyDashboard,
  parseExecutiveDashboard,
} from '../../lib/dashboard/contracts'
import { parseMonthlyProductionHistory } from '../../lib/dashboard/monthly-history-contracts'
import type { PhotovoltaicSummaryResponse } from '../../lib/dashboard/photovoltaic-contracts'
import { baselineUnavailableMessage, parsePhotovoltaicSummary } from '../../lib/dashboard/photovoltaic-contracts'
import { SectionTitle } from '../../components/SectionTitle'
import { EmptyState } from '../../components/EmptyState'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { MonthlyProductionSection } from '../../components/MonthlyProductionSection'
import { ProductionHistorySection, useProductionPeriodPreference } from '../../components/ProductionHistorySection'
import { RefreshBar } from '../../components/RefreshBar'
import { RetryableError } from '../../components/RetryableError'
import { PageHeader } from '../../components/PageHeader'
import { EnergyDestinationSection } from '../../components/EnergyDestinationSection'
import { DASHBOARD_TECHNICAL_PATH } from '../../routes'
import { MethodologyLink } from '../../components/MethodologyLink'

// Comparação com o esperado em chunk próprio: no primeiro ano da usina (sem
// referência) não aparece, então não precisa ser baixada (ADR-083, etapa 3).
const ExpectedComparisonSection = lazy(() =>
  import('../../components/ExpectedComparisonSection').then((module) => ({
    default: module.ExpectedComparisonSection,
  })),
)

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
  const headingRef = useModuleTitle('Energia')
  // Um período (7/30/90 dias) para o gráfico do topo e para a leitura do
  // período mais abaixo — os dois mostram sempre o mesmo recorte.
  const [periodDays, setPeriodDays] = useProductionPeriodPreference()

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
  // Ciclo da última fatura: para onde foi a energia (casa × rede). Veio da
  // antiga Visão Geral (ADR-083): é pergunta de energia, não de situação.
  const executive = usePlantResource({
    plantId,
    fetcher: fetchExecutiveDashboard,
    parse: parseExecutiveDashboard,
    errorMessage: 'Erro ao buscar o ciclo da fatura.',
  })
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
    executive.refetch()
    anomalies.refetch()
    pvSummaryResource.refetch()
    monthlyHistory.refetch()
  }
  // Combinado dos 3 recursos — usado pelo `disabled`/texto "Atualizando..."
  // do `RefreshBar`.
  const loading =
    executive.status === 'loading' ||
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

  // Comparação com o esperado (ADR-083, etapa 3). No primeiro ano da usina não
  // há referência: em vez de "—"/"Baseline indisponível" em seis lugares, um
  // aviso único diz quando ela começa, e os blocos que só existem contra o
  // esperado (régua do último dia, desvio, sequência, diagnóstico, episódios)
  // ficam de fora. Com erro no resumo FV, nada é afirmado sobre a referência.
  const hasBaseline = anomalies.data != null && anomalies.data.expected_unavailable_reason == null
  const baselineNotice =
    pvSummaryResource.status === 'success' && expectedProduction && !expectedProduction.available
      ? baselineUnavailableMessage(expectedProduction.reason, expectedProduction.referenceCompleteOn)
      : null

  return (
    <>
      <PageHeader
        eyebrow="Sua usina"
        title="Energia"
        description="Quanto a usina gerou e para onde foi."
        headingRef={headingRef}
        actions={<RefreshBar onRefresh={refreshAll} loading={loading} className="mb-0 lg:justify-self-end" />}
      />

      {baselineNotice && !hasBaseline && (
        <p
          role="note"
          className="mb-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-brand-primary-light)] px-4 py-3 text-[14px] leading-6 text-[var(--color-text-primary)]"
        >
          {baselineNotice}
        </p>
      )}

      {/* O mais importante primeiro: placas × distribuidora no período de cada
          fatura. Depois, para onde foi a energia e o dia a dia. */}
      <section className="mb-6">
        <SectionTitle as="h2">Placas × distribuidora, ciclo a ciclo</SectionTitle>
        {monthlyHistory.error ? (
          <RetryableError message={monthlyHistory.error} onRetry={monthlyHistory.refetch} />
        ) : (
          <MonthlyProductionSection history={monthlyHistory.data} plantId={plantId} />
        )}
      </section>

      {executive.data && (
        <EnergyDestinationSection
          indicators={executive.data.current_cycle.indicators}
          quality={executive.data.current_cycle.quality}
          referenceMonth={executive.data.current_cycle.reference_month}
        />
      )}

      <section className="mb-6">
        <SectionTitle as="h2">Histórico de produção</SectionTitle>
        <ProductionHistorySection
          layout="chart"
          anomalyState={anomalyState}
          expectedProduction={expectedProduction}
          onRetry={anomalies.refetch}
          periodDays={periodDays}
          onPeriodChange={setPeriodDays}
        />
      </section>

      <section className="mb-6">
        <ProductionHistorySection
          layout="details"
          detailsHeading="Leitura do período"
          anomalyState={anomalyState}
          expectedProduction={expectedProduction}
          onRetry={anomalies.refetch}
          periodDays={periodDays}
          onPeriodChange={setPeriodDays}
        />
      </section>

      {hasBaseline && (
        <Suspense fallback={<div className="mb-6 h-40 animate-pulse rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)]" aria-hidden="true" />}>
          <ExpectedComparisonSection
            anomalyState={anomalyState}
            expectedProduction={expectedProduction}
            onRetry={anomalies.refetch}
          />
        </Suspense>
      )}

      <Link
        to={DASHBOARD_TECHNICAL_PATH}
        className="mt-6 flex min-h-[56px] items-center justify-between gap-3 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4 shadow-[var(--shadow-card)] transition-colors duration-150 hover:border-[var(--color-gray-300)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none"
      >
        <span className="flex flex-col gap-0.5">
          <span className="text-[15px] font-semibold text-[var(--color-text-primary)]">Detalhes técnicos</span>
          <span className="text-[13px] text-[var(--color-text-secondary)]">Performance (PR), perdas, calor e inversores</span>
        </span>
        <span aria-hidden="true" className="text-[var(--color-gray-400)]">›</span>
      </Link>
      <MethodologyLink subtitle="Placas × distribuidora e a conferência dos créditos" />
    </>
  )
}
