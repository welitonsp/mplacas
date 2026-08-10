import { useState } from 'react'
import type { AnomalyFetchState, Severity } from '../lib/dashboard/contracts'
import {
  DEFAULT_PRODUCTION_PERIOD_DAYS,
  PRODUCTION_PERIOD_OPTIONS,
  averageActualProduction,
  latestProductionDays,
  productionAlertSignal,
  productionPerformancePercent,
  type ProductionPeriodDays,
} from '../lib/dashboard/production-alerts'
import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'
import { baselineUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { formatNumber, toNumber } from '../lib/format'
import { Card } from './Card'
import { EmptyState } from './EmptyState'
import { ProductionHistoryChart } from './ProductionHistoryChart'
import { RetryableError } from './RetryableError'
import { YieldCard } from './YieldCard'

const SIGNAL_STYLES: Record<Severity, string> = {
  success: 'border-[var(--color-success)]/20 bg-[var(--color-success-light)] text-[var(--color-success-text)]',
  warning: 'border-[var(--color-warning)]/25 bg-[var(--color-warning-light)] text-[var(--color-warning-text)]',
  danger: 'border-[var(--color-danger)]/25 bg-[var(--color-danger-light)] text-[var(--color-danger-text)]',
  neutral: 'border-gray-200 bg-gray-50 text-gray-700',
}

export function ProductionHistorySection({
  anomalyState,
  expectedProduction,
  onRetry,
}: {
  anomalyState: AnomalyFetchState
  // `null` = baseline sazonal ainda carregando.
  expectedProduction: ExpectedDailyProduction | null
  // Só relevante para o estado `SERVER_ERROR` — reexecuta a busca do histórico.
  onRetry?: () => void
}) {
  const [selectedPeriodDays, setSelectedPeriodDays] = useState<ProductionPeriodDays>(DEFAULT_PRODUCTION_PERIOD_DAYS)
  const loadingExpected = expectedProduction === null
  // Antes só esperava o histórico terminar de carregar quando a produção
  // esperada estava disponível — o que fazia o card pular direto pro
  // fallback de "indisponível" sem nunca checar se havia produção real
  // (ver diagnóstico do architect). Agora espera sempre, pra poder decidir
  // corretamente no bloco abaixo.
  const loadingHistory = anomalyState.loading && !anomalyState.data

  if (loadingExpected || loadingHistory) {
    return (
      <Card className="animate-pulse">
        <div className="mb-3 h-3 w-1/3 rounded bg-gray-200" />
        <div className="h-40 w-full rounded bg-gray-100" />
      </Card>
    )
  }

  // 404: ainda não há dado diário coletado para este período — estado esperado
  // (usina nova, backfill pendente), não é uma falha do sistema. Verificado
  // ANTES do bloco de "expectativa indisponível" abaixo: um erro de
  // fetch (404/500) precisa da mensagem específica dele, não da mensagem de
  // motivo de baseline — que só faz sentido quando o payload de anomalias
  // efetivamente chegou (200) e disse que não há expectativa.
  if (anomalyState.error === 'NOT_FOUND') {
    return (
      <EmptyState
        title="Sem histórico diário"
        description="Ainda não há dado de produção diária coletado para este período."
        tone="neutral"
      />
    )
  }

  // 5xx ou falha de rede: algo quebrou de fato — mensagem diferente e opção de
  // tentar novamente, em vez de misturar com o caso acima.
  if (anomalyState.error === 'SERVER_ERROR') {
    return (
      <RetryableError
        message="Não foi possível carregar o histórico de produção diária. Tente novamente."
        onRetry={onRetry ?? (() => {})}
      />
    )
  }

  if (!anomalyState.data) {
    return (
      <EmptyState
        title="Histórico indisponível"
        description="Não foi possível carregar o histórico de produção diária no momento."
        tone="neutral"
      />
    )
  }

  // Disponibilidade da expectativa derivada do PRÓPRIO payload de anomalias
  // (`expected_unavailable_reason`), não mais de `expectedProduction`
  // (`/photovoltaic/summary`, uma chamada de API separada) — as duas
  // acabavam divergindo entre si, ver contrato de `GET
  // /energy/anomalies/latest`. `expectedProduction` continua usado só para o
  // TEXTO específico do motivo (`baselineUnavailableMessage`), que reusa o
  // mesmo vocabulário de motivo do backend (`_derive_baseline_unavailable_reason`).
  const expectedAvailable = anomalyState.data.expected_unavailable_reason == null

  // Produção esperada indisponível (ver os três motivos em
  // `photovoltaic-contracts.ts`, ex.: baseline sazonal exige 366 dias de
  // histórico). Isso não significa que não exista produção real registrada —
  // o card de "produção esperada indisponível" só faz sentido quando também
  // não há dado de produção real nenhum. Havendo produção real, o gráfico
  // monta do mesmo jeito (sem a linha de comparação "esperado" — ver
  // `ProductionHistoryChart`/`expectedAvailable`), em vez de esconder um dado
  // que o usuário já tem (ver diagnóstico do architect).
  if (!expectedAvailable) {
    const hasActualProduction = anomalyState.data.daily.some(
      (d) => toNumber(d.actual_production_kwh) != null
    )

    if (!hasActualProduction) {
      return (
        <EmptyState
          title="Produção esperada indisponível"
          description={
            expectedProduction.available
              ? baselineUnavailableMessage('NO_PERFORMANCE_HISTORY', null)
              : baselineUnavailableMessage(expectedProduction.reason, expectedProduction.referenceCompleteOn)
          }
          tone="neutral"
        />
      )
    }
  }

  const filteredDaily = latestProductionDays(anomalyState.data.daily, selectedPeriodDays)
  const averageProduction = averageActualProduction(filteredDaily)
  const selectedPerformance = productionPerformancePercent(filteredDaily)
  const alertSignal = productionAlertSignal(anomalyState.data.daily)
  const hasIrradiation = filteredDaily.some((d) => toNumber(d.irradiation_kwh_m2) != null)

  return (
    <div className="space-y-4">
      <Card className="border-[var(--color-brand-primary)]/15 bg-[linear-gradient(135deg,var(--color-surface)_0%,var(--color-brand-primary-light)_100%)]">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-brand-primary)]">
              Produção diária
            </p>
            <h3 className="mt-1 text-lg font-semibold text-gray-950">
              Últimos {Math.min(selectedPeriodDays, anomalyState.data.daily.length)} dias em foco
            </h3>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-gray-600">
              O padrão inicial é 7 dias para detectar queda recente; 30 e 90 dias ajudam a confirmar se o problema é recorrente ou sazonal.
            </p>
          </div>

          <div className="flex flex-wrap gap-2" aria-label="Filtrar histórico diário">
            {PRODUCTION_PERIOD_OPTIONS.map((days) => {
              const active = selectedPeriodDays === days
              return (
                <button
                  key={days}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setSelectedPeriodDays(days)}
                  className={`min-h-[40px] rounded-full border px-3 text-sm font-semibold transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none ${
                    active
                      ? 'border-[var(--color-brand-primary)] bg-[var(--color-brand-primary)] text-white shadow-sm'
                      : 'border-gray-200 bg-[var(--color-surface)] text-gray-700 hover:-translate-y-0.5 hover:bg-white hover:text-gray-950 hover:shadow-sm'
                  }`}
                >
                  {days} dias
                </button>
              )
            })}
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl border border-gray-200 bg-[var(--color-surface)]/85 px-3 py-3">
            <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
              Média no período
            </p>
            <p className="mt-1 text-xl font-semibold text-gray-950 tabular-nums">
              {averageProduction.average == null ? '—' : `${formatNumber(averageProduction.average, 1)} kWh/dia`}
            </p>
            <p className="mt-1 text-xs text-gray-600">
              {averageProduction.days} {averageProduction.days === 1 ? 'dia com dado' : 'dias com dado'}
            </p>
          </div>

          <div className="rounded-2xl border border-gray-200 bg-[var(--color-surface)]/85 px-3 py-3">
            <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
              Desempenho médio
            </p>
            <p className="mt-1 text-xl font-semibold text-gray-950 tabular-nums">
              {selectedPerformance.percent == null ? '—' : `${formatNumber(selectedPerformance.percent, 1)}%`}
            </p>
            <p className="mt-1 text-xs text-gray-600">
              {selectedPerformance.assessedDays > 0
                ? `${selectedPerformance.assessedDays} dias contra esperado`
                : 'sem baseline no recorte'}
            </p>
          </div>

          <div className={`rounded-2xl border px-3 py-3 ${SIGNAL_STYLES[alertSignal.tone]}`}>
            <p className="text-[12px] font-semibold uppercase tracking-[0.14em] opacity-80">
              Gatilho de alerta
            </p>
            <p className="mt-1 text-xl font-semibold">
              {alertSignal.label}
            </p>
            <p className="mt-1 text-xs leading-5 opacity-85">
              {alertSignal.detail}
            </p>
          </div>
        </div>
      </Card>

      <div className={hasIrradiation ? 'grid grid-cols-1 gap-4 xl:grid-cols-[2fr_1fr]' : ''}>
        <ProductionHistoryChart
          daily={filteredDaily}
          currentStreakDays={anomalyState.data.current_streak_days}
          expectedAvailable={expectedAvailable}
        />
        <YieldCard daily={filteredDaily} />
      </div>
    </div>
  )
}
