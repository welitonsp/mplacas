import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { apiFetch, fetchFinancialReturn, fetchPhotovoltaicSummary } from '../lib/api'
import { PLANT_ID } from '../env'
import type { AnomalyFetchState, FetchState } from '../lib/dashboard/contracts'
import {
  classifyAnomalyErrorStatus,
  combineDiagnostics,
  latestNonNullProductionDate,
  parseAnomalyDashboard,
  parseExecutiveDashboard,
} from '../lib/dashboard/contracts'
import type { FinancialReturnResponse } from '../lib/dashboard/financial-return-contracts'
import { parseFinancialReturn } from '../lib/dashboard/financial-return-contracts'
import type { ExpectedDailyProduction, PhotovoltaicSummaryResponse } from '../lib/dashboard/photovoltaic-contracts'
import { deriveExpectedDailyProduction, parsePhotovoltaicSummary } from '../lib/dashboard/photovoltaic-contracts'
import { toNumber } from '../lib/format'
import { SectionTitle } from '../components/SectionTitle'
import { CurrencyCard } from '../components/CurrencyCard'
import { HeroCard } from '../components/HeroCard'
import { QualityBanner } from '../components/QualityBanner'
import { TrendCard } from '../components/TrendCard'
import { EnergyFlowDiagram } from '../components/EnergyFlowDiagram'
import { ExpectedProductionCard } from '../components/ExpectedProductionCard'
import { DashboardHeader } from '../components/DashboardHeader'
import { DiagnosticsCard } from '../components/DiagnosticsCard'
import { hasIncompleteDailyProduction } from '../components/EnergyProductionSection'
import { EstimatedSavingsCard } from '../components/EstimatedSavingsCard'
import { FinancialReturnSection } from '../components/FinancialReturnSection'
import { MetricCard } from '../components/MetricCard'
import { MetricCardSkeletonGrid } from '../components/MetricCardSkeletonGrid'
import { ProductionHistorySection } from '../components/ProductionHistorySection'
import { TechnicalPerformanceSection } from '../components/TechnicalPerformanceSection'

// Usado quando `/photovoltaic/summary` falha (rede ou erro de servidor, não
// 401): a seção de desempenho técnico mostra as mensagens de indisponibilidade
// por bloco em vez de ficar carregando indefinidamente — mesmo princípio de
// `expectedProduction` acima, aplicado a todos os blocos do resumo.
const FALLBACK_PV_SUMMARY: PhotovoltaicSummaryResponse = {
  plant_id: PLANT_ID,
  performance: null,
  performance_unavailable_reason: 'NO_PERFORMANCE_RESULTS',
  baseline: null,
  baseline_unavailable_reason: 'NO_PERFORMANCE_HISTORY',
  reference_complete_on: null,
  losses: null,
  losses_unavailable_reason: 'NO_LOSS_ASSESSMENTS',
}

export function DashboardPage() {
  const { logout } = useAuth()
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
  // `null` = ainda carregando o baseline sazonal. `/energy/anomalies/latest`
  // exige um `expected_daily_production_kwh` numérico positivo (ver
  // `intelligence/router.py`), então só disparamos essa busca depois de saber se
  // a usina tem baseline defensável — nunca inventamos um número de preenchimento.
  const [expectedProduction, setExpectedProduction] = useState<ExpectedDailyProduction | null>(null)
  // `null` = ainda carregando `/photovoltaic/summary` (mesma requisição de
  // `fetchExpectedProduction` — guardamos o resumo inteiro aqui para alimentar
  // `TechnicalPerformanceSection` sem uma segunda chamada de rede).
  const [pvSummary, setPvSummary] = useState<PhotovoltaicSummaryResponse | null>(null)
  // `null` = ainda carregando `/energy/financial-return/latest` (ADR-067). Erro de
  // rede/servidor fica em `financialReturnError`, separado do estado de
  // indisponibilidade de negócio (`unavailable_reason`), que é tratado dentro de
  // `FinancialReturnSection` — os dois nunca se confundem.
  const [financialReturn, setFinancialReturn] = useState<FinancialReturnResponse | null>(null)
  const [financialReturnError, setFinancialReturnError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const response = await apiFetch(
        `/energy/executive/latest?plant_id=${encodeURIComponent(PLANT_ID)}`
      )
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
  }, [])

  const fetchExpectedProduction = useCallback(async () => {
    setExpectedProduction(null)
    setPvSummary(null)
    try {
      const response = await fetchPhotovoltaicSummary(PLANT_ID)
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
        setPvSummary(FALLBACK_PV_SUMMARY)
        return
      }
      const summary = parsePhotovoltaicSummary(await response.json())
      setExpectedProduction(deriveExpectedDailyProduction(summary))
      setPvSummary(summary)
    } catch {
      setExpectedProduction({
        available: false,
        reason: 'NO_PERFORMANCE_HISTORY',
        referenceCompleteOn: null,
      })
      setPvSummary(FALLBACK_PV_SUMMARY)
    }
  }, [])

  const fetchFinancialReturnData = useCallback(async () => {
    setFinancialReturnError(null)
    try {
      const response = await fetchFinancialReturn(PLANT_ID)
      if (!response.ok) {
        if (response.status === 401) return
        throw new Error(`Erro ao buscar retorno do investimento (${response.status}).`)
      }
      setFinancialReturn(parseFinancialReturn(await response.json()))
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Erro ao buscar retorno do investimento.'
      setFinancialReturnError(message)
    }
  }, [])

  const fetchAnomalies = useCallback(async (expectedDailyProductionKwh: number) => {
    setAnomalyState((prev) => ({ ...prev, loading: true }))
    try {
      const response = await apiFetch(
        `/energy/anomalies/latest?plant_id=${encodeURIComponent(PLANT_ID)}` +
          `&expected_daily_production_kwh=${expectedDailyProductionKwh}&days=90`
      )
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
  }, [])

  useEffect(() => {
    void fetchData()
    void fetchExpectedProduction()
    void fetchFinancialReturnData()
  }, [fetchData, fetchExpectedProduction, fetchFinancialReturnData])

  // O histórico de produção/anomalias só é buscado depois que sabemos a produção
  // esperada real da usina — sem ela o endpoint de anomalias não tem contra o que
  // comparar o dia (ver `fetchAnomalies` acima).
  useEffect(() => {
    if (expectedProduction === null) return
    if (expectedProduction.available) {
      void fetchAnomalies(expectedProduction.kwh)
    } else {
      setAnomalyState({ data: null, loading: false, error: null })
    }
  }, [expectedProduction, fetchAnomalies])

  const retryAnomalies = useCallback(() => {
    if (expectedProduction?.available) void fetchAnomalies(expectedProduction.kwh)
  }, [expectedProduction, fetchAnomalies])

  const { data, loading, error, lastUpdated } = state
  const indicators = data?.current_cycle.indicators
  const quality = data?.current_cycle.quality
  const latestDataDate = anomalyState.data ? latestNonNullProductionDate(anomalyState.data.daily) : null
  // Calculado uma única vez e reusado pelo chip do Hero (`AttentionSummary`,
  // ver Etapa 1.7) e pela lista completa (`DiagnosticsCard`) — mesma lista,
  // duas apresentações.
  const diagnostics = data ? combineDiagnostics(data) : []

  return (
    <div className="min-h-screen bg-gray-50">
      <DashboardHeader onLogout={logout} />

      <main className="mx-auto max-w-7xl 2xl:max-w-[96rem] px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col gap-3 mb-6 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-sm font-medium text-gray-600">Dashboard executivo</h2>
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                void fetchData()
                void fetchExpectedProduction()
                void fetchFinancialReturnData()
              }}
              disabled={loading}
              className="rounded text-xs text-[var(--color-brand-primary)] hover:text-[var(--color-brand-primary-dark)] disabled:opacity-50 transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
            >
              {loading ? 'Atualizando...' : 'Atualizar'}
            </button>
          </div>
        </div>

        {error && (
          <div
            role="alert"
            className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[var(--color-danger-light)] border border-[var(--color-danger)]/20 px-4 py-3 text-sm text-[var(--color-danger)]"
          >
            <span>{error}</span>
            {/* Retry associado diretamente ao erro global (não só o link
                "Atualizar" no topo da página, que existia mas não estava
                visualmente ligado à mensagem — ver P2-08 na auditoria de
                UI/UX). Mesmo padrão de `ProductionHistorySection` para o
                erro de servidor do histórico de produção. */}
            <button
              type="button"
              onClick={() => {
                void fetchData()
                void fetchExpectedProduction()
              }}
              className="shrink-0 rounded text-sm font-medium text-[var(--color-danger-text)] hover:underline transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-danger)]"
            >
              Tentar novamente
            </button>
          </div>
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

            {/* Histórico de produção diária — bloco maior (gráfico), ao lado
                da produção real vs. esperada. Já forma duas colunas reais a
                partir de `md` (768px) — não só em `lg` (ver P1-04). */}
            <section className="md:col-span-4 lg:col-span-8 2xl:col-span-9">
              <SectionTitle>Histórico de produção</SectionTitle>
              <ProductionHistorySection
                anomalyState={anomalyState}
                expectedProduction={expectedProduction}
                onRetry={retryAnomalies}
              />
            </section>

            <section className="md:col-span-2 lg:col-span-4 2xl:col-span-3">
              <SectionTitle>Produção real vs. esperada</SectionTitle>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-4">
                <MetricCard
                  label="Produção no ciclo"
                  value={indicators.cycle_production_kwh}
                  unit="kWh"
                  partial={hasIncompleteDailyProduction(quality)}
                  className="h-full"
                />
                <ExpectedProductionCard expectedProduction={expectedProduction} className="h-full" />
              </div>
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
              <SectionTitle>Fluxo de energia</SectionTitle>
              <EnergyFlowDiagram
                production={indicators.cycle_production_kwh}
                selfConsumption={indicators.estimated_self_consumption_kwh}
                injected={indicators.injected_kwh}
                imported={indicators.imported_kwh}
                consumption={indicators.estimated_total_consumption_kwh}
              />
            </section>

            {/* Diagnósticos e comparação com o ciclo anterior, empilhados na
                mesma coluna estreita. `id` é o alvo da âncora do chip de
                atenção no Hero (ver `AttentionSummary`, Etapa 1.7). */}
            <section id="diagnosticos" className="md:col-span-3 lg:col-span-5">
              <DiagnosticsCard diagnostics={diagnostics} />

              {data.trend && (
                <div className="mt-8">
                  <SectionTitle>Tendência</SectionTitle>
                  <TrendCard trend={data.trend} />
                </div>
              )}
            </section>

            {/* Bloco próprio — "Como está o desempenho técnico?": PR, PR
                corrigido por temperatura, yield específico, disponibilidade de
                reporte, degradação anualizada e atribuição de causa de perda.
                Responde "está indo bem?" com granularidade técnica maior que o
                Bloco 1 acima — por isso vira seção own em vez de subseção
                dentro dele (ver Etapa 6), posicionada logo depois porque ainda
                é sobre "produção/desempenho", antes do Bloco 2 mudar o foco
                para "para onde foi a energia". */}
            <section className="md:col-span-6 lg:col-span-12">
              <SectionTitle>Desempenho técnico</SectionTitle>
              <TechnicalPerformanceSection summary={pvSummary} />
            </section>

            {/* "Energia e produção" (importada/injetada/autoconsumo/consumo)
                foi removida da composição — os mesmos quatro números já
                aparecem em "Fluxo de energia" (`EnergyFlowDiagram`), com a
                relação entre eles, que os cards isolados não davam (ver
                P2-01). O componente `EnergyProductionSection` continua
                existindo em `components/` para reuso futuro, só não compõe
                mais esta página. */}
            <section className="md:col-span-6 lg:col-span-12">
              <SectionTitle>Indicadores percentuais</SectionTitle>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <MetricCard
                  label="Autossuficiência"
                  value={indicators.self_sufficiency_rate_percent}
                  unit="%"
                  barPercent={toNumber(indicators.self_sufficiency_rate_percent)}
                />
                <MetricCard
                  label="Dependência da rede"
                  value={indicators.grid_dependency_rate_percent}
                  unit="%"
                  barPercent={toNumber(indicators.grid_dependency_rate_percent)}
                />
              </div>
            </section>

            {/* Bloco 3 — "Quanto custou?": financeiro completo (Etapa 7).
                Valores em R$ (total da fatura, componente de energia,
                iluminação pública, economia estimada), tarifas em R$/kWh e
                saldo/cobertura de créditos — cada card com unidade sempre
                visível, sem exceção para a economia quando a tarifa não está
                registrada (ver EstimatedSavingsCard). */}
            <section className="md:col-span-6 lg:col-span-12">
              <SectionTitle>Financeiro</SectionTitle>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <CurrencyCard label="Valor total da fatura" value={indicators.total_amount_brl} />
                <CurrencyCard
                  label="Componente energia da fatura"
                  value={indicators.bill_energy_component_brl}
                />
                <CurrencyCard label="Iluminação pública" value={indicators.public_lighting_brl} />
                <EstimatedSavingsCard
                  value={indicators.estimated_savings_brl}
                  unavailableReason={indicators.savings_unavailable_reason}
                />
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
                <MetricCard label="Saldo de créditos" value={indicators.credit_balance_kwh} unit="kWh" />
                <MetricCard
                  label="Cobertura de créditos"
                  value={indicators.credit_coverage_rate_percent}
                  unit="%"
                  barPercent={toNumber(indicators.credit_coverage_rate_percent)}
                />
              </div>
            </section>

            {/* Retorno do investimento (ADR-067, Etapa E): CAPEX, ROI acumulado e
                projeção de payback, logo depois do Bloco 3 ("Quanto custou?") —
                mesma pergunta financeira, num horizonte mais longo. Card único,
                mais estreito que o grid acima (o conteúdo é uma barra de progresso
                mais dois blocos de texto, não uma grade de métricas). */}
            <section className="md:col-span-6 lg:col-span-12">
              <SectionTitle>Retorno do investimento</SectionTitle>
              {financialReturnError ? (
                <div
                  role="alert"
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[var(--color-danger-light)] border border-[var(--color-danger)]/20 px-4 py-3 text-sm text-[var(--color-danger-text)]"
                >
                  <span>{financialReturnError}</span>
                  <button
                    type="button"
                    onClick={() => void fetchFinancialReturnData()}
                    className="shrink-0 rounded text-sm font-medium hover:underline transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-danger)]"
                  >
                    Tentar novamente
                  </button>
                </div>
              ) : (
                <div className="max-w-xl">
                  <FinancialReturnSection
                    financialReturn={financialReturn}
                    plantId={PLANT_ID}
                    onInvestmentRegistered={() => void fetchFinancialReturnData()}
                  />
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  )
}
