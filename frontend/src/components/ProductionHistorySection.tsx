import type { AnomalyFetchState } from '../lib/dashboard/contracts'
import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'
import { baselineUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { toNumber } from '../lib/format'
import { Card } from './Card'
import { ProductionHistoryChart } from './ProductionHistoryChart'
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

  // Produção esperada indisponível (ver os três motivos em
  // `photovoltaic-contracts.ts`, ex.: baseline sazonal exige 366 dias de
  // histórico). Isso não significa que não exista produção real registrada —
  // o card de "produção esperada indisponível" só faz sentido quando também
  // não há dado de produção real nenhum. Havendo produção real, o gráfico
  // monta do mesmo jeito (sem a linha de comparação "esperado" — ver
  // `ProductionHistoryChart`/`expectedAvailable`), em vez de esconder um dado
  // que o usuário já tem (ver diagnóstico do architect).
  if (!expectedProduction.available) {
    const hasActualProduction =
      anomalyState.data?.daily.some((d) => toNumber(d.actual_production_kwh) != null) ?? false

    if (!hasActualProduction) {
      return (
        <Card>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Histórico de produção diária
          </p>
          <p className="mt-4 text-sm text-gray-500">
            {baselineUnavailableMessage(expectedProduction.reason, expectedProduction.referenceCompleteOn)}
          </p>
        </Card>
      )
    }
  }

  // 404: ainda não há dado diário coletado para este período — estado esperado
  // (usina nova, backfill pendente), não é uma falha do sistema.
  if (anomalyState.error === 'NOT_FOUND') {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Histórico de produção diária
        </p>
        <p className="mt-4 text-sm text-[var(--color-text-secondary)]">
          Ainda não há dado de produção diária coletado para este período.
        </p>
      </Card>
    )
  }

  // 5xx ou falha de rede: algo quebrou de fato — mensagem diferente e opção de
  // tentar novamente, em vez de misturar com o caso acima.
  if (anomalyState.error === 'SERVER_ERROR') {
    return (
      <Card tone="danger">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Histórico de produção diária
        </p>
        <p className="mt-4 text-sm text-[var(--color-danger)]">
          Não foi possível carregar o histórico de produção diária. Tente novamente.
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 rounded text-xs font-medium text-[var(--color-brand-primary)] hover:text-[var(--color-brand-primary-dark)] transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
          >
            Tentar novamente
          </button>
        )}
      </Card>
    )
  }

  if (!anomalyState.data) {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Histórico de produção diária
        </p>
        <p className="mt-4 text-sm text-gray-500">
          Não foi possível carregar o histórico de produção diária no momento.
        </p>
      </Card>
    )
  }

  const hasIrradiation = anomalyState.data.daily.some((d) => toNumber(d.irradiation_kwh_m2) != null)

  return (
    <div className={hasIrradiation ? 'grid grid-cols-1 gap-4 xl:grid-cols-[2fr_1fr]' : ''}>
      <ProductionHistoryChart
        daily={anomalyState.data.daily}
        currentStreakDays={anomalyState.data.current_streak_days}
        expectedAvailable={expectedProduction.available}
      />
      <YieldCard daily={anomalyState.data.daily} />
    </div>
  )
}
