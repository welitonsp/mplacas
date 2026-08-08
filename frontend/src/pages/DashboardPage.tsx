import {
  fetchAnomalyHistory,
  fetchExecutiveDashboard,
  fetchFinancialReturn,
  fetchMonthlyProductionHistory,
  fetchPhotovoltaicSummary,
} from '../lib/api'
import { usePlant } from '../contexts/PlantContext'
import { usePlantResource } from '../hooks/usePlantResource'
import type { AnomalyDashboardResponse, AnomalyFetchError, AnomalyFetchState } from '../lib/dashboard/contracts'
import {
  classifyAnomalyErrorStatus,
  combineDiagnostics,
  latestNonNullProductionDate,
  parseAnomalyDashboard,
  parseExecutiveDashboard,
} from '../lib/dashboard/contracts'
import { parseFinancialReturn } from '../lib/dashboard/financial-return-contracts'
import { parseMonthlyProductionHistory } from '../lib/dashboard/monthly-history-contracts'
import type { PhotovoltaicSummaryResponse } from '../lib/dashboard/photovoltaic-contracts'
import { parsePhotovoltaicSummary } from '../lib/dashboard/photovoltaic-contracts'
import { formatNumber, toNumber } from '../lib/format'
import { SectionTitle } from '../components/SectionTitle'
import { StackedBar } from '../components/charts/StackedBar'
import { HeroCard } from '../components/HeroCard'
import { QualityBanner } from '../components/QualityBanner'
import { TrendCard } from '../components/TrendCard'
import { EnergyFlowDiagram } from '../components/EnergyFlowDiagram'
import { DiagnosticsCard } from '../components/DiagnosticsCard'
import { hasIncompleteDailyProduction } from '../components/EnergyProductionSection'
import { FinancialSection } from '../components/FinancialSection'
import { LatestDailyProductionCard } from '../components/LatestDailyProductionCard'
import { MetricCard } from '../components/MetricCard'
import { MetricCardSkeletonGrid } from '../components/MetricCardSkeletonGrid'
import { MonthlyProductionSection } from '../components/MonthlyProductionSection'
import { ProductionHistorySection } from '../components/ProductionHistorySection'
import { RetryableError } from '../components/RetryableError'

// Usado quando `/photovoltaic/summary` falha (rede ou erro de servidor, não
// 401): garante um `expectedProduction.available: false` explícito para
// `ProductionHistorySection` em vez de deixar a seção carregando
// indefinidamente. `plant_id` depende da usina ativa (`PlantContext`,
// ADR-069), por isso vira função em vez de constante de módulo.
//
// ADR-072 (Etapa 2): o restante deste resumo (performance/baseline/losses)
// não é mais consumido por esta página — só `expectedProduction` continua
// sendo, via `TechnicalPerformanceSection`, que migrou para
// `pages/dashboard/TechnicalPage.tsx` (cópia local desta mesma função lá).
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

export function DashboardPage() {
  const { plantId, plants, loading: plantsLoading, error: plantsError } = usePlant()
  // `null` (`.data`) = ainda carregando `/energy/executive/latest`. Migrado para
  // `usePlantResource` (Etapa 4): o hook cobre a mesma proteção de race
  // condition/troca de usina que o fetch manual anterior fazia à mão. Erro de
  // rede/servidor fica em `executive.error` (mensagem fixa, sem sufixo de status
  // HTTP — o detalhe vai para o console via o próprio hook, mesma política de
  // `financialReturn`/`monthlyHistory` abaixo).
  const executive = usePlantResource({
    plantId,
    fetcher: fetchExecutiveDashboard,
    parse: parseExecutiveDashboard,
    errorMessage: 'Erro ao buscar dados.',
  })
  // `null` (`.data`) = ainda carregando `/energy/anomalies/latest`. Migrado para
  // `usePlantResource` (Etapa 5) — desde a mudança de contrato deste endpoint
  // (200 sempre, campos por dia `null` sem expectativa), este recurso NÃO
  // depende de `pvSummaryResource` abaixo: é buscado assim que há `plantId`,
  // independente do baseline sazonal já existir (ver usina com produção real
  // mas sem baseline — o card de histórico não pode ficar preso esperando um
  // dado que talvez nunca chegue). `classifyError` reusa `classifyAnomalyErrorStatus`
  // (já testado isoladamente em `contracts.test.ts`): 404 vira `'NOT_FOUND'`, 5xx
  // vira `'SERVER_ERROR'`, e 401 já volta `null` de dentro da própria função —
  // falha silenciosa, mesma política de antes (`apiFetch` já tentou refresh; se
  // falhou, o usuário está sendo deslogado, não há nada a comunicar aqui). Falha
  // de rede/contrato (`kind !== 'http'`) cai no mesmo `'SERVER_ERROR'`, mesma
  // categoria de "algo quebrou" que um 5xx no comportamento anterior.
  const anomalies = usePlantResource<AnomalyDashboardResponse, AnomalyFetchError>({
    plantId,
    fetcher: fetchAnomalyHistory,
    parse: parseAnomalyDashboard,
    classifyError: (failure) =>
      failure.kind === 'http' ? classifyAnomalyErrorStatus(failure.status) : 'SERVER_ERROR',
  })
  // Adapta o resultado de `usePlantResource` de volta ao shape `AnomalyFetchState`
  // que `ProductionHistorySection`/`LatestDailyProductionCard` já esperam — o
  // contrato de prop desses dois componentes (e seus testes) não muda nesta etapa.
  const anomalyState: AnomalyFetchState = {
    data: anomalies.data,
    loading: anomalies.status === 'loading',
    error: anomalies.error,
  }
  // `null` (`.data`) = ainda carregando `/photovoltaic/summary`. Migrado para
  // `usePlantResource` (Etapa 4). `errorMessage` aqui só alimenta o
  // `console.error` do hook: esta seção nunca expõe o erro na tela — em caso
  // de falha, a derivação de `pvSummary`/`expectedProduction` logo abaixo das
  // guardas de render cai em `fallbackPvSummary`, que já traz um motivo de
  // indisponibilidade explícito por bloco.
  const pvSummaryResource = usePlantResource({
    plantId,
    fetcher: fetchPhotovoltaicSummary,
    parse: parsePhotovoltaicSummary,
    errorMessage: 'Erro ao buscar resumo fotovoltaico.',
  })
  // `null` (`.data`) = ainda carregando `/energy/financial-return/latest` (ADR-067).
  // Migrado para `usePlantResource` (Etapa 3): o hook cobre a mesma proteção de
  // race condition/troca de usina que o fetch manual anterior fazia à mão. Erro de
  // rede/servidor fica em `financialReturn.error` (mensagem fixa, sem sufixo de
  // status HTTP — o detalhe vai para o console via o próprio hook), separado do
  // estado de indisponibilidade de negócio (`unavailable_reason`), que é tratado
  // dentro de `FinancialReturnSection` — os dois nunca se confundem.
  const financialReturn = usePlantResource({
    plantId,
    fetcher: fetchFinancialReturn,
    parse: parseFinancialReturn,
    errorMessage: 'Erro ao buscar retorno do investimento.',
  })
  // `null` (`.data`) = ainda carregando `/reports/monthly/history` (histórico de
  // produção por ciclo de faturamento). Mesmo padrão de `financialReturn` acima.
  // `fetcher` precisa de um wrapper porque `fetchMonthlyProductionHistory` recebe
  // `limit` como segundo parâmetro, que a assinatura de `usePlantResource.fetcher`
  // não conhece.
  const monthlyHistory = usePlantResource({
    plantId,
    fetcher: (id: string) => fetchMonthlyProductionHistory(id, 12),
    parse: parseMonthlyProductionHistory,
    errorMessage: 'Erro ao buscar histórico de produção.',
  })

  // Refetch único para os 5 recursos (Etapa 6) — usado tanto pelo botão
  // "Atualizar" quanto pelo `RetryableError` do erro global. Antes, o botão
  // já refazia os 5 na mão (repetido inline) e o banner de erro global só
  // refazia o executivo, deixando os outros 4 recursos presos no estado
  // antigo mesmo depois do usuário pedir para tentar de novo.
  const refreshAll = () => {
    executive.refetch()
    anomalies.refetch()
    pvSummaryResource.refetch()
    financialReturn.refetch()
    monthlyHistory.refetch()
  }
  // Combinado dos 5 recursos — usado pelo `disabled`/texto "Atualizando..."
  // do botão "Atualizar" (o nome `loading` é preservado de propósito: o
  // teste `DashboardPage.focusVisible.test.tsx` casa a fonte literal do
  // JSX do botão mais abaixo (ver ternário loading/"Atualizando"/"Atualizar");
  // renomear a variável quebraria o teste sem nenhuma mudança de
  // comportamento real).
  const loading =
    executive.status === 'loading' ||
    anomalies.status === 'loading' ||
    pvSummaryResource.status === 'loading' ||
    financialReturn.status === 'loading' ||
    monthlyHistory.status === 'loading'

  const data = executive.data
  // Usado só pelo esqueleto de carregamento do bloco principal (linha
  // `{loading && !data && ...}` abaixo) — continua amarrado especificamente
  // ao recurso executivo, que é quem preenche `data`. Não confundir com
  // `loading` (combinado, Etapa 6) usado pelo botão "Atualizar": os dois têm
  // propósitos diferentes e podem divergir (ex.: executivo já respondeu com
  // erro mas outro recurso ainda está em voo — o esqueleto não deve
  // reaparecer por cima do banner de erro global).
  const executiveLoading = executive.status === 'loading'
  const error = executive.error
  const lastUpdated = executive.lastUpdated
  const indicators = data?.current_cycle.indicators
  const quality = data?.current_cycle.quality
  // Autossuficiência e dependência da rede são complementares (somam 100%) —
  // convertidos uma única vez para alimentar a `StackedBar` unificada
  // (ver seção "Indicadores percentuais" abaixo).
  const selfSufficiencyPercent = toNumber(indicators?.self_sufficiency_rate_percent ?? null)
  const gridDependencyPercent = toNumber(indicators?.grid_dependency_rate_percent ?? null)
  // A decomposição da fatura (total/energia/iluminação pública) e o restante
  // do bloco financeiro (custo do ciclo, tarifas, créditos, retorno do
  // investimento) vivem em `FinancialSection` (Etapa 7) — só o `indicators`
  // do ciclo corrente e o recurso `financialReturn` cruzam a fronteira.
  const latestDataDate = anomalyState.data ? latestNonNullProductionDate(anomalyState.data.daily) : null
  // Calculado uma única vez e reusado pelo chip do Hero (`AttentionSummary`,
  // ver Etapa 1.7) e pela lista completa (`DiagnosticsCard`) — mesma lista,
  // duas apresentações.
  const diagnostics = data ? combineDiagnostics(data) : []

  // Enquanto a lista de usinas (`PlantContext`) ainda carrega, nenhuma
  // requisição de dados do dashboard foi disparada — mostra o mesmo
  // esqueleto de carregamento usado para os dados do ciclo.
  if (plantsLoading) {
    return <MetricCardSkeletonGrid />
  }

  // Falha ao carregar `/plants`: sem usina resolvida, não há como buscar dado
  // nenhum do dashboard.
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
      <div className="rounded-lg border border-gray-200 bg-[var(--color-surface)] px-6 py-10 text-center text-sm text-gray-600">
        Nenhuma usina cadastrada para esta conta ainda.
      </div>
    )
  }

  // A partir daqui `plantId` está estreitado para `string` pelas guardas
  // acima — só agora é seguro chamar `fallbackPvSummary(plantId)` (Etapa 4).
  // Cai no fallback só quando `pvSummaryResource.status === 'error'`:
  // enquanto `'loading'` (inclusive num refetch da MESMA usina, que preserva
  // o `data` anterior em vez de zerar — ver `usePlantResource`), `pvSummary`
  // reflete o `data` já resolvido ou `null` enquanto a primeira resposta
  // ainda não chegou, nunca o fallback prematuramente.
  const pvSummary = pvSummaryResource.status === 'error' ? fallbackPvSummary(plantId) : pvSummaryResource.data
  const expectedProduction = pvSummary?.expectedProduction ?? null

  return (
    <>
      {/* Sem `<h2>` isolado aqui: a casca do app (`AppHeader`) já identifica a
          página, e um segundo título genérico logo abaixo era redundante —
          só a barra de ação (botão "Atualizar") permanece. */}
      <div className="flex flex-col gap-3 mb-6 sm:flex-row sm:items-center sm:justify-end">
        <div className="flex items-center gap-3">
          <button
            onClick={refreshAll}
            disabled={loading}
            className="rounded text-xs text-[var(--color-brand-primary)] hover:text-[var(--color-brand-primary-dark)] disabled:opacity-50 transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
          >
            {loading ? 'Atualizando...' : 'Atualizar'}
          </button>
        </div>
      </div>

      {error && (
        // Retry associado diretamente ao erro global (não só o link
        // "Atualizar" no topo da página, que existia mas não estava
        // visualmente ligado à mensagem — ver P2-08 na auditoria de
        // UI/UX). Mesmo padrão de `ProductionHistorySection` para o
        // erro de servidor do histórico de produção.
        <RetryableError
          message={error}
          onRetry={refreshAll}
          className="mb-6"
        />
      )}

      {executiveLoading && !data && <MetricCardSkeletonGrid />}

        {data && indicators && quality && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-6 lg:grid-cols-12 lg:gap-6 items-start">
            {/* Bloco 1 — "Está indo bem?": saúde do ciclo e status de qualidade
                do ciclo, em uma faixa horizontal full-width. */}
            <section className="md:col-span-6 lg:col-span-12">
              <HeroCard
                referenceMonth={data.current_cycle.reference_month}
                headline={data.headline}
                status={data.status}
                healthScore={indicators.health_score}
                latestDataDate={latestDataDate}
                lastSyncedAt={lastUpdated}
                diagnostics={diagnostics}
              />
              <QualityBanner quality={quality} />
            </section>

            {/* Produção por ciclo de faturamento (12 ciclos fechados) — leitura
                do grosso pro fino: o resumo mensal primeiro, o histórico
                diário de 90 dias (bloco seguinte) depois. Erro desta seção é
                isolado (`monthlyHistory.error`) e não trava o resto do
                dashboard se a chamada falhar. */}
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

            {/* Histórico de produção diária — bloco maior (gráfico), ao lado
                da produção real vs. esperada. Já forma duas colunas reais a
                partir de `md` (768px) — não só em `lg` (ver P1-04). */}
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
              {/* Compara o último dia com dado diário coletado (real vs.
                  esperado, mesma escala kWh/dia) — não mais o total do ciclo
                  (~30 dias) contra uma média diária, comparação que produzia
                  um desvio percentual absurdo. A produção do ciclo continua
                  visível no nó "Produção" de `EnergyFlowDiagram` abaixo. */}
              <LatestDailyProductionCard anomalyState={anomalyState} className="h-full" />
              {/* A frase de streak abaixo do esperado aparece só dentro do
                  gráfico de histórico (ver `ProductionHistoryChart`) — este
                  bloco chegou a duplicá-la lado a lado com o gráfico em
                  `lg+`; mantida uma única vez, no lugar onde o contexto
                  diário (qual dia, qual nível) já está visível (ver P2-02). */}
            </section>

            {/* Bloco 2 — "Para onde foi a energia?": um único diagrama de
                fluxo (autoconsumo/injetada/importada não se repetem em mais
                visuais — ver Etapa 5), detalhamento numérico e histórico. */}
            <section className="md:col-span-3 lg:col-span-7">
              <SectionTitle as="h2">Fluxo de energia</SectionTitle>
              <EnergyFlowDiagram
                production={indicators.cycle_production_kwh}
                selfConsumption={indicators.estimated_self_consumption_kwh}
                injected={indicators.injected_kwh}
                imported={indicators.imported_kwh}
                consumption={indicators.estimated_total_consumption_kwh}
                partial={hasIncompleteDailyProduction(quality)}
              />
            </section>

            {/* Diagnósticos e comparação com o ciclo anterior, empilhados na
                mesma coluna estreita. `id` é o alvo da âncora do chip de
                atenção no Hero (ver `AttentionSummary`, Etapa 1.7). */}
            <section id="diagnosticos" className="md:col-span-3 lg:col-span-5">
              <DiagnosticsCard diagnostics={diagnostics} />

              {data.trend && (
                <div className="mt-8">
                  <SectionTitle as="h2">Tendência</SectionTitle>
                  <TrendCard trend={data.trend} />
                </div>
              )}
            </section>

            {/* "Energia e produção" (importada/injetada/autoconsumo/consumo)
                foi removida da composição — os mesmos quatro números já
                aparecem em "Fluxo de energia" (`EnergyFlowDiagram`), com a
                relação entre eles, que os cards isolados não davam (ver
                P2-01). O componente `EnergyProductionSection` continua
                existindo em `components/` para reuso futuro, só não compõe
                mais esta página. */}
            <section className="md:col-span-6 lg:col-span-12">
              <SectionTitle as="h2">Indicadores percentuais</SectionTitle>
              {/* Autossuficiência e dependência da rede são complementares
                  (somam 100%) — antes eram dois `MetricCard` soltos com dois
                  números sem relação visual entre si (P2-03, fechado agora
                  por decisão do usuário). Uma única `StackedBar` de 2
                  segmentos deixa a proporção explícita. Se qualquer um dos
                  dois vier `null`, mantém os cards separados em vez de
                  fabricar a barra com metade do dado ausente. */}
              {selfSufficiencyPercent != null && gridDependencyPercent != null ? (
                <StackedBar
                  segments={[
                    { label: 'Autossuficiência', value: selfSufficiencyPercent, tone: 'success' },
                    { label: 'Dependência da rede', value: gridDependencyPercent, tone: 'neutral' },
                  ]}
                  total={100}
                  valueFormatter={(value) => `${formatNumber(value, 1)}%`}
                />
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <MetricCard
                    label="Autossuficiência"
                    value={indicators.self_sufficiency_rate_percent}
                    unit="%"
                    barPercent={selfSufficiencyPercent}
                  />
                  <MetricCard
                    label="Dependência da rede"
                    value={indicators.grid_dependency_rate_percent}
                    unit="%"
                    barPercent={gridDependencyPercent}
                  />
                </div>
              )}
            </section>

            {/* Bloco 3 — "Quanto custou? Qual o retorno?": financeiro
                completo, extraído para `FinancialSection` (Etapa 7) — custo
                do ciclo, tarifas, créditos e retorno do investimento juntos,
                dois `<section>` irmãos dentro do mesmo componente (ver
                comentário em `FinancialSection.tsx`). */}
            <FinancialSection indicators={indicators} financialReturn={financialReturn} plantId={plantId} />

            {/* O bloco "Como está o desempenho técnico?" (PR, yield
                específico, disponibilidade de reporte, degradação e
                atribuição de causa de perda) migrou para o módulo próprio em
                `pages/dashboard/TechnicalPage.tsx` (ADR-072, Etapa 2) — não
                aparece mais aqui, para não duplicar entre as rotas
                `/dashboard/tecnico` e esta página (ainda servindo as outras
                3 rotas até as próximas etapas migrarem). */}
          </div>
        )}
    </>
  )
}
