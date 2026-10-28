import { useState } from 'react'
import type { AnomalyFetchState, Severity } from '../lib/dashboard/contracts'
import {
  DEFAULT_PRODUCTION_PERIOD_DAYS,
  PRODUCTION_PERIOD_OPTIONS,
  compareProductionAverageTrend,
  latestProductionDays,
  productionAlertSignal,
  type ProductionPeriodDays,
} from '../lib/dashboard/production-alerts'
import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'
import { baselineUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { toNumber } from '../lib/format'
import { Card } from './Card'
import { SectionTitle } from './SectionTitle'
import { EmptyState } from './EmptyState'
import { ProductionHistoryChart } from './ProductionHistoryChart'
import { RetryableError } from './RetryableError'
import { YieldCard } from './YieldCard'
import { safeStorage } from '../lib/storage'

// Só a cor do TEXTO do sinal (ADR-077): o rótulo de estado carrega a cor,
// o bloco em volta fica neutro — antes cada sinal era uma caixa colorida.
const SIGNAL_TEXT: Record<Severity, string> = {
  success: 'text-[var(--color-success-text)]',
  warning: 'text-[var(--color-warning-text)]',
  danger: 'text-[var(--color-danger-text)]',
  neutral: 'text-[var(--color-text-primary)]',
}

const PERIOD_STORAGE_KEY = 'mplacas:production-history-period'

function parseStoredPeriodPreference(value: string | null): ProductionPeriodDays {
  const period = Number(value)

  if (Number.isFinite(period) && PRODUCTION_PERIOD_OPTIONS.includes(period as ProductionPeriodDays)) {
    return period as ProductionPeriodDays
  }

  return DEFAULT_PRODUCTION_PERIOD_DAYS
}

function readStoredPeriodPreference(): ProductionPeriodDays {
  if (typeof window === 'undefined') {
    return DEFAULT_PRODUCTION_PERIOD_DAYS
  }

  try {
    return parseStoredPeriodPreference(safeStorage.get(PERIOD_STORAGE_KEY))
  } catch {
    return DEFAULT_PRODUCTION_PERIOD_DAYS
  }
}

function saveStoredPeriodPreference(days: ProductionPeriodDays) {
  if (typeof window === 'undefined') {
    return
  }

  try {
    safeStorage.set(PERIOD_STORAGE_KEY, String(days))
  } catch {
    // LocalStorage pode estar bloqueado em alguns navegadores/modos privados.
    // A seleção visual continua funcionando pela memória do React.
  }
}

/**
 * Período do histórico diário (7/30/90) com preferência lembrada. Exposto para
 * a página compartilhar UM período entre o gráfico (no topo do módulo) e a
 * leitura do período (mais abaixo) — os dois sempre mostram o mesmo recorte.
 */
export function useProductionPeriodPreference(): [ProductionPeriodDays, (days: ProductionPeriodDays) => void] {
  const [days, setDays] = useState<ProductionPeriodDays>(readStoredPeriodPreference)
  const select = (next: ProductionPeriodDays) => {
    setDays(next)
    saveStoredPeriodPreference(next)
  }
  return [days, select]
}

// `all`: seletor + leitura do período + gráfico + rendimento (uso isolado).
// `chart`: só o gráfico, com o seletor de período no próprio cartão — é o que
//   fica logo abaixo do resumo operacional (pedido do dono do produto).
// `details`: leitura do período + rendimento, sem seletor (o seletor está no
//   gráfico); não repete carregamento/erro, que o gráfico já mostra.
export type ProductionHistoryLayout = 'all' | 'chart' | 'details'

export function ProductionHistorySection({
  anomalyState,
  expectedProduction,
  onRetry,
  layout = 'all',
  periodDays,
  onPeriodChange,
  detailsHeading,
}: {
  anomalyState: AnomalyFetchState
  // `null` = baseline sazonal ainda carregando.
  expectedProduction: ExpectedDailyProduction | null
  // Só relevante para o estado `SERVER_ERROR` — reexecuta a busca do histórico.
  onRetry?: () => void
  layout?: ProductionHistoryLayout
  // Controlado pela página quando `chart` e `details` aparecem separados;
  // sem estas props o componente guarda o próprio período (uso isolado).
  periodDays?: ProductionPeriodDays
  onPeriodChange?: (days: ProductionPeriodDays) => void
  // Título da seção em `details` — só aparece quando há conteúdo, para não
  // sobrar um título solto enquanto o gráfico mostra carregando/erro.
  detailsHeading?: string
}) {
  const [ownPeriodDays, setOwnPeriodDays] = useProductionPeriodPreference()
  const selectedPeriodDays = periodDays ?? ownPeriodDays
  const loadingExpected = expectedProduction === null
  // Antes só esperava o histórico terminar de carregar quando a produção
  // esperada estava disponível — o que fazia o card pular direto pro
  // fallback de "indisponível" sem nunca checar se havia produção real
  // (ver diagnóstico do architect). Agora espera sempre, pra poder decidir
  // corretamente no bloco abaixo.
  const loadingHistory = anomalyState.loading && !anomalyState.data

  // Em `details`, carregamento/erro/vazio já aparecem no gráfico acima —
  // repetir aqui seria o mesmo aviso duas vezes na tela.
  const dataReady =
    !loadingExpected &&
    !loadingHistory &&
    anomalyState.error == null &&
    anomalyState.data != null &&
    (anomalyState.data.expected_unavailable_reason == null ||
      anomalyState.data.daily.some((d) => toNumber(d.actual_production_kwh) != null))

  if (layout === 'details' && !dataReady) {
    return null
  }

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
  const averageTrend = compareProductionAverageTrend(anomalyState.data.daily, selectedPeriodDays)
  const alertSignal = productionAlertSignal(anomalyState.data.daily)
  const hasIrradiation = filteredDaily.some((d) => toNumber(d.irradiation_kwh_m2) != null)

  function handlePeriodSelect(days: ProductionPeriodDays) {
    if (onPeriodChange) {
      onPeriodChange(days)
    } else {
      setOwnPeriodDays(days)
    }
  }

  const periodSelector = (
    <div
      role="group"
      aria-label="Filtrar histórico diário"
      className="inline-flex rounded-[var(--radius-control)] border border-[var(--color-border)] bg-[var(--color-surface-sunken)] p-1"
    >
      {PRODUCTION_PERIOD_OPTIONS.map((days) => {
        const active = selectedPeriodDays === days
        return (
          <button
            key={days}
            type="button"
            aria-pressed={active}
            onClick={() => handlePeriodSelect(days)}
            className={`min-h-[44px] rounded-lg px-3.5 text-sm transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none ${
              active
                ? 'bg-[var(--color-surface)] font-semibold text-[var(--color-text-primary)] shadow-[0_1px_2px_rgb(0_0_0_/_0.12)]'
                : 'font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
            }`}
          >
            {days} dias
          </button>
        )
      })}
    </div>
  )

  const chart = (
    <ProductionHistoryChart
      daily={filteredDaily}
      currentStreakDays={anomalyState.data.current_streak_days}
      expectedAvailable={expectedAvailable}
      headerAction={layout === 'chart' ? periodSelector : undefined}
      tall={layout === 'chart'}
    />
  )

  if (layout === 'chart') {
    return chart
  }

  // `details` com rendimento disponível: os dois cards lado a lado no desktop
  // (orientação paisagem), empilhados no celular. Sem rendimento agregado
  // (mesma condição em que o `YieldCard` não renderiza), "Produção diária"
  // ocupa a largura toda em vez de deixar uma coluna vazia.
  const landscape = layout === 'details' && toNumber(anomalyState.data.period_yield_kwh_per_kwh_m2) != null

  return (
    <div className="space-y-4">
      {layout === 'details' && detailsHeading && <SectionTitle as="h2">{detailsHeading}</SectionTitle>}
      <div className={landscape ? 'grid grid-cols-1 items-stretch gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:gap-6' : 'space-y-4'}>
      <Card className={landscape ? 'h-full sm:p-6' : 'sm:p-6'}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">Produção diária</p>
            <h3 className="mt-1 text-lg font-semibold text-[var(--color-text-primary)]">
              Últimos {Math.min(selectedPeriodDays, anomalyState.data.daily.length)} dias em foco
            </h3>
            <p className="mt-1 max-w-2xl text-[13px] leading-5 text-[var(--color-text-secondary)]">
              Troque o período para ver se uma variação é passageira (7 dias) ou se repete (30 e 90 dias).
            </p>
          </div>

          {layout === 'all' && periodSelector}
        </div>

        <dl
          className="mt-5 grid grid-cols-1 gap-x-6 gap-y-5 border-t border-[var(--color-border)] pt-5 sm:grid-cols-2"
        >
          {/* "Média no período" e "Desempenho médio" saíram daqui: o gráfico
              logo acima já mostra os dois (linha "Média N" e "Desempenho: N%"
              no cabeçalho). ADR-077, decisão 15 — cada número uma vez por
              tela. Ficam só os sinais que o gráfico não mostra. */}
          <div className="min-w-0">
            <dt className="text-[13px] font-medium text-[var(--color-text-secondary)]">Tendência do recorte</dt>
            <dd className={`mt-1 text-[17px] font-semibold ${SIGNAL_TEXT[averageTrend.tone]}`}>{averageTrend.label}</dd>
            <dd className="text-xs leading-5 text-[var(--color-text-secondary)]">{averageTrend.detail}</dd>
          </div>

          <div className="min-w-0">
            <dt className="text-[13px] font-medium text-[var(--color-text-secondary)]">Gatilho de alerta</dt>
            <dd className={`mt-1 text-[17px] font-semibold ${SIGNAL_TEXT[alertSignal.tone]}`}>{alertSignal.label}</dd>
            <dd className="text-xs leading-5 text-[var(--color-text-secondary)]">{alertSignal.detail}</dd>
          </div>
        </dl>
      </Card>

      {landscape ? (
        <YieldCard
          daily={anomalyState.data.daily}
          periodYieldKwhPerKwhM2={anomalyState.data.period_yield_kwh_per_kwh_m2}
          yieldAtypicalThresholdPercent={anomalyState.data.yield_atypical_threshold_percent}
          periodYieldSampleDays={anomalyState.data.period_yield_sample_days}
          period={anomalyState.data.period}
          className="h-full"
        />
      ) : (
      <div className={layout === 'all' && hasIrradiation ? 'grid grid-cols-1 gap-4 xl:grid-cols-[2fr_1fr]' : ''}>
        {layout === 'all' && chart}
        {/* `YieldCard` recebe `anomalyState.data.daily` INTEIRO, não
            `filteredDaily` (plano T7b, P0: "o card afirma o que não
            verificou"). `period_yield_kwh_per_kwh_m2`/
            `yield_deviation_from_median_percent` de cada dia já vêm do
            backend calculados sobre a janela cheia analisada (hoje até 90
            dias, ver `lib/api.ts::fetchAnomalyHistory` — este módulo sempre
            busca o máximo, `filteredDaily` é só um recorte visual client-side
            do seletor de período acima). Passar `filteredDaily` faria o
            cabeçalho anunciar "N dias analisados" tendo varrido só o
            recorte visível — e faria a lista de dias atípicos mudar ao
            trocar o recorte sem o cabeçalho acompanhar. */}
        <YieldCard
          daily={anomalyState.data.daily}
          periodYieldKwhPerKwhM2={anomalyState.data.period_yield_kwh_per_kwh_m2}
          yieldAtypicalThresholdPercent={anomalyState.data.yield_atypical_threshold_percent}
          periodYieldSampleDays={anomalyState.data.period_yield_sample_days}
          period={anomalyState.data.period}
        />
      </div>
      )}
      </div>
    </div>
  )
}
