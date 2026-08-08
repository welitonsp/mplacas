import { fetchPhotovoltaicSummary } from '../../lib/api'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import type { PhotovoltaicSummaryResponse } from '../../lib/dashboard/photovoltaic-contracts'
import { parsePhotovoltaicSummary } from '../../lib/dashboard/photovoltaic-contracts'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { RetryableError } from '../../components/RetryableError'
import { TechnicalPerformanceSection } from '../../components/TechnicalPerformanceSection'

// Usado quando `/photovoltaic/summary` falha (rede ou erro de servidor, não
// 401): a seção mostra as mensagens de indisponibilidade por bloco em vez de
// ficar carregando indefinidamente. Cópia local da mesma função em
// `DashboardPage.tsx` — cada módulo tem sua própria instância de
// `usePlantResource` (ADR-072, Decisão 3: fronteira de fetch por módulo, sem
// estado compartilhado entre módulos), e `DashboardPage.tsx` ainda precisa
// da sua própria cópia para derivar `expectedProduction`, consumido por
// `ProductionHistorySection` até o módulo Produção migrar (Etapa 4).
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

// Módulo Técnico (ADR-072, Etapa 2) — o menor dos 4, um único recurso
// (`/photovoltaic/summary`, ver ADR seção 2). Sem o toggle expandir/colapsar
// que `TechnicalPerformanceSection` tinha antes desta etapa: a rota já é a
// divulgação progressiva.
export function TechnicalPage() {
  const { plantId, plants, loading: plantsLoading, error: plantsError } = usePlant()

  const pvSummaryResource = usePlantResource({
    plantId,
    fetcher: fetchPhotovoltaicSummary,
    parse: parsePhotovoltaicSummary,
    errorMessage: 'Erro ao buscar resumo fotovoltaico.',
  })

  // Enquanto a lista de usinas (`PlantContext`) ainda carrega, nenhuma
  // requisição deste módulo foi disparada — mesmo esqueleto de carregamento
  // usado por `DashboardPage` para o mesmo estado.
  if (plantsLoading) {
    return <MetricCardSkeletonGrid />
  }

  // Falha ao carregar `/plants`: sem usina resolvida, não há como buscar
  // `/photovoltaic/summary`.
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
  // acima. Cai no fallback só quando `pvSummaryResource.status === 'error'`
  // — enquanto `'loading'` (inclusive num refetch da MESMA usina, que
  // preserva o `data` anterior em vez de zerar), `pvSummary` reflete o
  // `data` já resolvido ou `null` enquanto a primeira resposta ainda não
  // chegou, nunca o fallback prematuramente (mesmo comportamento de
  // `DashboardPage`).
  const pvSummary = pvSummaryResource.status === 'error' ? fallbackPvSummary(plantId) : pvSummaryResource.data

  return <TechnicalPerformanceSection summary={pvSummary} />
}
