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
  const loadingHistory = expectedProduction?.available === true && anomalyState.loading && !anomalyState.data

  if (loadingExpected || loadingHistory) {
    return (
      <Card className="animate-pulse">
        <div className="mb-3 h-3 w-1/3 rounded bg-gray-200" />
        <div className="h-40 w-full rounded bg-gray-100" />
      </Card>
    )
  }

  // Produção esperada indisponível (ver os três motivos em
  // `photovoltaic-contracts.ts`): sem ela o backend não classifica anomalia por
  // dia, então nem chegamos a buscar o histórico. Mostramos o motivo específico
  // em vez de um card vazio (ver skill frontend-design).
  if (!expectedProduction.available) {
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
    <div className={hasIrradiation ? 'grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]' : ''}>
      <ProductionHistoryChart
        daily={anomalyState.data.daily}
        currentStreakDays={anomalyState.data.current_streak_days}
      />
      <YieldCard daily={anomalyState.data.daily} />
    </div>
  )
}
