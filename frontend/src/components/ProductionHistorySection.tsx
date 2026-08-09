import type { AnomalyFetchState } from '../lib/dashboard/contracts'
import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'
import { baselineUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { toNumber } from '../lib/format'
import { Card } from './Card'
import { EmptyState } from './EmptyState'
import { ProductionHistoryChart } from './ProductionHistoryChart'
import { RetryableError } from './RetryableError'
import { YieldCard } from './YieldCard'

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

  const hasIrradiation = anomalyState.data.daily.some((d) => toNumber(d.irradiation_kwh_m2) != null)

  return (
    <div className={hasIrradiation ? 'grid grid-cols-1 gap-4 xl:grid-cols-[2fr_1fr]' : ''}>
      <ProductionHistoryChart
        daily={anomalyState.data.daily}
        currentStreakDays={anomalyState.data.current_streak_days}
        expectedAvailable={expectedAvailable}
      />
      <YieldCard daily={anomalyState.data.daily} />
    </div>
  )
}
