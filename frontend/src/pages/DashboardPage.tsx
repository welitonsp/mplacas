import { useCallback, useEffect, useState } from 'react'
import {
  fetchAnomalyHistory,
  fetchExecutiveDashboard,
  fetchFinancialReturn,
  fetchMonthlyProductionHistory,
  fetchPhotovoltaicSummary,
} from '../lib/api'
import { usePlant } from '../contexts/PlantContext'
import { usePlantResource } from '../hooks/usePlantResource'
import type { AnomalyFetchState, FetchState } from '../lib/dashboard/contracts'
import {
  classifyAnomalyErrorStatus,
  combineDiagnostics,
  latestNonNullProductionDate,
  parseAnomalyDashboard,
  parseExecutiveDashboard,
} from '../lib/dashboard/contracts'
import { parseFinancialReturn } from '../lib/dashboard/financial-return-contracts'
import { parseMonthlyProductionHistory } from '../lib/dashboard/monthly-history-contracts'
import type { ExpectedDailyProduction, PhotovoltaicSummaryResponse } from '../lib/dashboard/photovoltaic-contracts'
import { parsePhotovoltaicSummary } from '../lib/dashboard/photovoltaic-contracts'
import { formatCurrency, formatNumber, toNumber } from '../lib/format'
import { SectionTitle } from '../components/SectionTitle'
import { CurrencyCard } from '../components/CurrencyCard'
import { StackedBar } from '../components/charts/StackedBar'
import { HeroCard } from '../components/HeroCard'
import { QualityBanner } from '../components/QualityBanner'
import { TrendCard } from '../components/TrendCard'
import { EnergyFlowDiagram } from '../components/EnergyFlowDiagram'
import { DiagnosticsCard } from '../components/DiagnosticsCard'
import { hasIncompleteDailyProduction } from '../components/EnergyProductionSection'
import { EstimatedSavingsCard } from '../components/EstimatedSavingsCard'
import { FinancialReturnSection } from '../components/FinancialReturnSection'
import { LatestDailyProductionCard } from '../components/LatestDailyProductionCard'
import { MetricCard } from '../components/MetricCard'
import { MetricCardSkeletonGrid } from '../components/MetricCardSkeletonGrid'
import { MonthlyProductionSection } from '../components/MonthlyProductionSection'
import { ProductionHistorySection } from '../components/ProductionHistorySection'
import { RetryableError } from '../components/RetryableError'
import { TechnicalPerformanceSection } from '../components/TechnicalPerformanceSection'

// Usado quando `/photovoltaic/summary` falha (rede ou erro de servidor, não
// 401): a seção de desempenho técnico mostra as mensagens de indisponibilidade
// por bloco em vez de ficar carregando indefinidamente — mesmo princípio de
// `expectedProduction` acima, aplicado a todos os blocos do resumo.
// `plant_id` depende da usina ativa (`PlantContext`, ADR-069), por isso vira
// função em vez de constante de módulo.
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
  const [state, setState] = useState<FetchState>({
    data: null,
    loading: true,
    error: null,
    lastUpdated: null,
  })
  const [anomalyState, setAnomalyState] = useState<AnomalyFetchState>({
    data: null,
    loading: true,
    error: null,
  })
  // `null` = ainda carregando o baseline sazonal (`/photovoltaic/summary`).
  // Usado só para alimentar `TechnicalPerformanceSection` e as mensagens de
  // motivo específico de indisponibilidade — desde a mudança de contrato de
  // `/energy/anomalies/latest` (200 sempre, campos por dia `null` sem
  // expectativa), `fetchAnomalies` NÃO depende mais deste estado: é buscado
  // assim que há `plantId`, independente do baseline sazonal já existir (ver
  // usina com produção real mas sem baseline — o card de histórico não pode
  // mais ficar preso esperando um dado que talvez nunca chegue).
  const [expectedProduction, setExpectedProduction] = useState<ExpectedDailyProduction | null>(null)
  // `null` = ainda carregando `/photovoltaic/summary` (mesma requisição de
  // `fetchExpectedProduction` — guardamos o resumo inteiro aqui para alimentar
  // `TechnicalPerformanceSection` sem uma segunda chamada de rede).
  const [pvSummary, setPvSummary] = useState<PhotovoltaicSummaryResponse | null>(null)
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

  const fetchData = useCallback(async () => {
    if (!plantId) return
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const response = await fetchExecutiveDashboard(plantId)
      if (!response.ok) {
        if (response.status === 401) {
          // apiFetch already attempted refresh; if still 401 the user was logged out.
          return
        }
        throw new Error(`Erro ao buscar dados (${response.status}).`)
      }
      const data = parseExecutiveDashboard(await response.json())
      setState({ data, loading: false, error: null, lastUpdated: new Date() })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido ao buscar dados.'
      setState((prev) => ({ ...prev, loading: false, error: message }))
    }
  }, [plantId])

  const fetchExpectedProduction = useCallback(async () => {
    if (!plantId) return
    setExpectedProduction(null)
    setPvSummary(null)
    try {
      const response = await fetchPhotovoltaicSummary(plantId)
      if (!response.ok) {
        if (response.status === 401) return
        // Sessão expirada à parte, um erro aqui não deve travar o resto do
        // dashboard — o histórico de produção e a seção de desempenho técnico
        // passam a mostrar o motivo de indisponibilidade específico assim que
        // souberem que não há dado, em vez de ficar carregando para sempre.
        setExpectedProduction({
          available: false,
          reason: 'NO_PERFORMANCE_HISTORY',
          referenceCompleteOn: null,
        })
        setPvSummary(fallbackPvSummary(plantId))
        return
      }
      const summary = parsePhotovoltaicSummary(await response.json())
      setExpectedProduction(summary.expectedProduction)
      setPvSummary(summary)
    } catch {
      setExpectedProduction({
        available: false,
        reason: 'NO_PERFORMANCE_HISTORY',
        referenceCompleteOn: null,
      })
      setPvSummary(fallbackPvSummary(plantId))
    }
  }, [plantId])

  const fetchAnomalies = useCallback(async () => {
    if (!plantId) return
    setAnomalyState((prev) => ({ ...prev, loading: true }))
    try {
      const response = await fetchAnomalyHistory(plantId)
      if (!response.ok) {
        // 404 (sem dado diário ainda) e 5xx (algo quebrou) recebem mensagens
        // diferentes em `ProductionHistorySection` — ver `classifyAnomalyErrorStatus`.
        // 401 continua silencioso: `apiFetch` já tentou refresh, e se falhou o
        // usuário está sendo deslogado, não há nada a comunicar aqui.
        setAnomalyState({ data: null, loading: false, error: classifyAnomalyErrorStatus(response.status) })
        return
      }
      const data = parseAnomalyDashboard(await response.json())
      setAnomalyState({ data, loading: false, error: null })
    } catch {
      // Falha de rede: mesma categoria de "algo quebrou" que um 5xx.
      setAnomalyState({ data: null, loading: false, error: 'SERVER_ERROR' })
    }
  }, [plantId])

  // `financialReturn`/`monthlyHistory` não precisam de chamada explícita aqui —
  // `usePlantResource` já dispara a busca sozinho a cada mudança de `plantId`.
  useEffect(() => {
    void fetchData()
    void fetchExpectedProduction()
    void fetchAnomalies()
  }, [fetchData, fetchExpectedProduction, fetchAnomalies])

  const retryAnomalies = useCallback(() => {
    void fetchAnomalies()
  }, [fetchAnomalies])

  const { data, loading, error, lastUpdated } = state
  const indicators = data?.current_cycle.indicators
  const quality = data?.current_cycle.quality
  // Autossuficiência e dependência da rede são complementares (somam 100%) —
  // convertidos uma única vez para alimentar a `StackedBar` unificada
  // (ver seção "Indicadores percentuais" abaixo).
  const selfSufficiencyPercent = toNumber(indicators?.self_sufficiency_rate_percent ?? null)
  const gridDependencyPercent = toNumber(indicators?.grid_dependency_rate_percent ?? null)
  // Decomposição da fatura (Parte C): `bill_energy_component_brl` é definido
  // no backend como `total_amount_brl - public_lighting_brl` (clamped em 0,
  // ver intelligence/energy_engine.py::analyze_energy_cycle) — a soma dos
  // dois sempre reconstrói o total, então "resto" existe só para cobrir um
  // eventual encargo futuro não capturado por essas duas categorias, nunca
  // para absorver uma inconsistência de parser. Se qualquer um dos três
  // valores vier `null`, mantém os `CurrencyCard` separados.
  const billTotalAmount = toNumber(indicators?.total_amount_brl ?? null)
  const billEnergyComponent = toNumber(indicators?.bill_energy_component_brl ?? null)
  const billPublicLighting = toNumber(indicators?.public_lighting_brl ?? null)
  const billOtherCharges =
    billTotalAmount != null && billEnergyComponent != null && billPublicLighting != null
      ? billTotalAmount - billEnergyComponent - billPublicLighting
      : null
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

  return (
    <>
      {/* Sem `<h2>` isolado aqui: a casca do app (`AppHeader`) já identifica a
          página, e um segundo título genérico logo abaixo era redundante —
          só a barra de ação (botão "Atualizar") permanece. */}
      <div className="flex flex-col gap-3 mb-6 sm:flex-row sm:items-center sm:justify-end">
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              void fetchData()
              void fetchExpectedProduction()
              void fetchAnomalies()
              monthlyHistory.refetch()
              financialReturn.refetch()
            }}
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
          onRetry={() => {
            void fetchData()
            void fetchExpectedProduction()
          }}
          className="mb-6"
        />
      )}

      {loading && !data && <MetricCardSkeletonGrid />}

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
                onRetry={retryAnomalies}
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

            {/* Bloco 3 — "Quanto custou?": financeiro completo (Etapa 7).
                Valores em R$ (total da fatura, componente de energia,
                iluminação pública, economia estimada), tarifas em R$/kWh e
                saldo/cobertura de créditos — cada card com unidade sempre
                visível, sem exceção para a economia quando a tarifa não está
                registrada (ver EstimatedSavingsCard). */}
            <section className="md:col-span-6 lg:col-span-12">
              <SectionTitle as="h2">Financeiro</SectionTitle>
              {/* Os mesmos oito cards de antes, reagrupados em três
                  subseções rotuladas em vez de uma grade achatada — a
                  hierarquia visual (fatura vs. tarifa vs. créditos) já
                  existia na cabeça de quem lê, só não estava expressa na
                  estrutura (acabamento de hierarquia do dashboard). */}
              <div className="space-y-6">
                <div>
                  <SectionTitle>Custo do ciclo</SectionTitle>
                  {/* Decomposição da fatura (energia + iluminação pública [+
                      outros encargos, quando a soma não fecha em cima dos
                      dois conhecidos]) — antes eram três `CurrencyCard`
                      soltos sem nenhuma indicação visual de que compunham o
                      mesmo total. Validado contra o parser real
                      (`bill_energy_component_brl = total_amount_brl -
                      public_lighting_brl`, ver `intelligence/energy_engine.py`)
                      antes de decompor — ver skill `financial-visualization`. */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
                    {billTotalAmount != null && billEnergyComponent != null && billPublicLighting != null ? (
                      <div className="rounded-lg border border-gray-200 bg-[var(--color-surface)] p-4">
                        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                          Valor total da fatura
                        </p>
                        <p className="mt-1 mb-3 text-2xl font-semibold text-gray-900 tabular-nums">
                          {formatCurrency(billTotalAmount)}
                        </p>
                        <StackedBar
                          segments={[
                            { label: 'Componente energia', value: billEnergyComponent, tone: 'neutral' },
                            { label: 'Iluminação pública', value: billPublicLighting, tone: 'warning' },
                            ...(billOtherCharges != null && billOtherCharges > 0.005
                              ? [{ label: 'Outros encargos', value: billOtherCharges, tone: 'danger' as const }]
                              : []),
                          ]}
                          total={billTotalAmount}
                          valueFormatter={formatCurrency}
                        />
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 lg:col-span-2">
                        <CurrencyCard label="Valor total da fatura" value={indicators.total_amount_brl} />
                        <CurrencyCard
                          label="Componente energia da fatura"
                          value={indicators.bill_energy_component_brl}
                        />
                        <CurrencyCard label="Iluminação pública" value={indicators.public_lighting_brl} />
                      </div>
                    )}
                    <EstimatedSavingsCard
                      value={indicators.estimated_savings_brl}
                      unavailableReason={indicators.savings_unavailable_reason}
                    />
                  </div>
                </div>

                <div>
                  <SectionTitle>Tarifas</SectionTitle>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <MetricCard
                      label="Tarifa com impostos"
                      value={indicators.tariff_with_taxes_brl_kwh}
                      unit="R$/kWh"
                      maximumFractionDigits={6}
                    />
                    <MetricCard
                      label="Tarifa sem impostos"
                      value={indicators.tariff_without_taxes_brl_kwh}
                      unit="R$/kWh"
                      maximumFractionDigits={6}
                    />
                  </div>
                </div>

                <div>
                  <SectionTitle>Créditos de energia</SectionTitle>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <MetricCard label="Saldo de créditos" value={indicators.credit_balance_kwh} unit="kWh" />
                    <MetricCard
                      label="Cobertura de créditos"
                      value={indicators.credit_coverage_rate_percent}
                      unit="%"
                      barPercent={toNumber(indicators.credit_coverage_rate_percent)}
                    />
                  </div>
                </div>
              </div>
            </section>

            {/* Retorno do investimento (ADR-067, Etapa E): CAPEX, ROI acumulado e
                projeção de payback, logo depois do Bloco 3 ("Quanto custou?") —
                mesma pergunta financeira, num horizonte mais longo. Card único,
                mais estreito que o grid acima (o conteúdo é uma barra de progresso
                mais dois blocos de texto, não uma grade de métricas). */}
            <section className="md:col-span-6 lg:col-span-12">
              <SectionTitle as="h2">Retorno do investimento</SectionTitle>
              {financialReturn.error ? (
                <RetryableError
                  message={financialReturn.error}
                  onRetry={financialReturn.refetch}
                />
              ) : (
                plantId && (
                  <div className="max-w-xl">
                    <FinancialReturnSection
                      financialReturn={financialReturn.data}
                      plantId={plantId}
                      onInvestmentRegistered={financialReturn.refetch}
                    />
                  </div>
                )
              )}
            </section>

            {/* Bloco próprio — "Como está o desempenho técnico?": PR, PR
                corrigido por temperatura, yield específico, disponibilidade de
                reporte, degradação anualizada e atribuição de causa de perda.
                Responde "está indo bem?" com granularidade técnica maior que o
                Bloco 1 acima — por isso vira seção own em vez de subseção
                dentro dele (ver Etapa 6). Reordenada para depois do bloco
                Financeiro/Retorno do investimento (Etapa 3.2, P2-04 parcial):
                "quanto custou" e "qual o retorno" respondem à pergunta mais
                prática de um dono de usina antes da granularidade técnica de
                PR/yield/degradação, que agora também está colapsada por
                padrão (ver `TechnicalPerformanceSection`, Etapa 3.4). */}
            <section className="md:col-span-6 lg:col-span-12">
              <TechnicalPerformanceSection summary={pvSummary} />
            </section>
          </div>
        )}
    </>
  )
}
