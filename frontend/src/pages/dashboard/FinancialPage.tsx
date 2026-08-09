import { fetchExecutiveDashboard, fetchFinancialReturn } from '../../lib/api'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import { parseExecutiveDashboard } from '../../lib/dashboard/contracts'
import { parseFinancialReturn } from '../../lib/dashboard/financial-return-contracts'
import { FinancialSection } from '../../components/FinancialSection'
import { EmptyState } from '../../components/EmptyState'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { RefreshBar } from '../../components/RefreshBar'
import { RetryableError } from '../../components/RetryableError'

// Módulo Financeiro (ADR-072, Etapa 3) — dois recursos (ver ADR seção 2):
// `executive` (`/energy/executive/latest`) e `financialReturn`
// (`/energy/financial-return/latest`). Não existe um endpoint "resumo
// financeiro" dedicado — `FinancialSection` consome `current_cycle.indicators`
// (custo do ciclo, tarifas, créditos) e `current_cycle.reference_month`
// (exibido junto do bloco "Custo do ciclo" — achado F1 da auditoria
// financeira desta sessão: uma tarifa com 6 casas decimais sem o ciclo ao
// lado não é reproduzível a partir da fatura confirmada que a originou, ver
// ADR-056 seção sobre variação de tarifa entre ciclos) do payload executivo,
// por isso este módulo precisa do recurso executivo inteiro mesmo sem usar
// `headline`/`status`/`trend`/diagnósticos, que pertencem à Visão Geral
// (Etapa 5).
export function FinancialPage() {
  const { plantId, plants, loading: plantsLoading, error: plantsError } = usePlant()
  // `document.title`/foco por rota (ADR-072, Etapa 6) — ver `useModuleTitle`.
  // Chamado antes de qualquer `return` condicional abaixo (regra dos hooks).
  const headingRef = useModuleTitle('Financeiro')

  const executive = usePlantResource({
    plantId,
    fetcher: fetchExecutiveDashboard,
    parse: parseExecutiveDashboard,
    errorMessage: 'Erro ao buscar dados.',
  })
  // `null` (`.data`) = ainda carregando `/energy/financial-return/latest`
  // (ADR-067). Erro de rede/servidor fica em `financialReturn.error`, tratado
  // por `FinancialSection` (RetryableError substitui o card de retorno do
  // investimento) — não duplicado aqui.
  const financialReturn = usePlantResource({
    plantId,
    fetcher: fetchFinancialReturn,
    parse: parseFinancialReturn,
    errorMessage: 'Erro ao buscar retorno do investimento.',
  })

  // Refetch único para os 2 recursos deste módulo — usado pelo botão
  // "Atualizar" (`RefreshBar`). O erro do recurso executivo continua com seu
  // próprio retry no banner global (`RetryableError` abaixo); este botão só
  // força uma nova tentativa dos 2 recursos ao mesmo tempo.
  const refreshAll = () => {
    executive.refetch()
    financialReturn.refetch()
  }
  // Combinado dos 2 recursos — usado pelo `disabled`/texto "Atualizando..."
  // do `RefreshBar`.
  const loading = executive.status === 'loading' || financialReturn.status === 'loading'

  // Enquanto a lista de usinas (`PlantContext`) ainda carrega, nenhuma
  // requisição deste módulo foi disparada — mesmo esqueleto de carregamento
  // usado por `DashboardPage`/`TechnicalPage` para o mesmo estado.
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
        description="Nenhuma usina cadastrada para esta conta ainda. Quando uma usina for vinculada, economia, retorno e créditos aparecerão aqui."
        tone="brand"
      />
    )
  }

  const data = executive.data
  const indicators = data?.current_cycle.indicators
  const executiveLoading = executive.status === 'loading'

  return (
    <>
      {/* `<h1>` próprio do módulo (ADR-072, Etapa 6) — ver o mesmo comentário
          em `OverviewPage.tsx`. Sempre visível (inclusive durante erro/
          carregamento do recurso executivo), igual aos outros 3 módulos. */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-[var(--color-brand-primary)]">
            Painel financeiro
          </p>
          <h1 ref={headingRef} tabIndex={-1} className="mt-1 text-2xl font-bold text-gray-900 tracking-tight focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] rounded">
            Financeiro
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--color-text-secondary)]">
            Leitura do ciclo, créditos de energia e retorno do investimento em uma visão preparada para decisão.
          </p>
        </div>
        <RefreshBar onRefresh={refreshAll} loading={loading} className="mb-0 lg:justify-self-end" />
      </div>

      {executive.error && (
        <RetryableError
          message={executive.error}
          onRetry={executive.refetch}
          className="mb-6"
        />
      )}

      {executiveLoading && !data && <MetricCardSkeletonGrid />}

      {data && indicators && (
        // Mesma grade de 12 colunas de `DashboardPage`: `FinancialSection`
        // devolve dois `<section>` irmãos (`md:col-span-6 lg:col-span-12`
        // cada), preservados sem mudança de layout ao migrar de módulo.
        <div className="grid grid-cols-1 gap-4 md:grid-cols-6 lg:grid-cols-12 lg:gap-6 items-start">
          <FinancialSection
            indicators={indicators}
            referenceMonth={data.current_cycle.reference_month}
            financialReturn={financialReturn}
            plantId={plantId}
          />
        </div>
      )}
    </>
  )
}
