import { lazy, Suspense } from 'react'
import { fetchExecutiveDashboard, fetchFinancialReturn, fetchInvestorPanel } from '../../lib/api'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import { parseExecutiveDashboard } from '../../lib/dashboard/contracts'
import { parseFinancialReturn } from '../../lib/dashboard/financial-return-contracts'
import { parseInvestorPanel } from '../../lib/dashboard/investor-contracts'
import { FinancialSection } from '../../components/FinancialSection'
import { EmptyState } from '../../components/EmptyState'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { RefreshBar } from '../../components/RefreshBar'
import { RetryableError } from '../../components/RetryableError'
import { PageHeader } from '../../components/PageHeader'
import { BillsSection } from '../../components/BillsSection'

// Painel do investidor sob demanda: chunk próprio (gráfico de patrimônio +
// premissas), para não estourar o teto de 15 kB do módulo Financeiro.
const InvestorPanelSection = lazy(() =>
  import('../../components/InvestorPanelSection').then((module) => ({
    default: module.InvestorPanelSection,
  })),
)

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

  // Painel do investidor (ADR-079): usina × CDI líquido, realizado e projeção.
  const investor = usePlantResource({
    plantId,
    fetcher: fetchInvestorPanel,
    parse: parseInvestorPanel,
    errorMessage: 'Erro ao buscar a comparação com o CDI.',
  })

  // Refetch único para os 2 recursos deste módulo — usado pelo botão
  // "Atualizar" (`RefreshBar`). O erro do recurso executivo continua com seu
  // próprio retry no banner global (`RetryableError` abaixo); este botão só
  // força uma nova tentativa dos 2 recursos ao mesmo tempo.
  const refreshAll = () => {
    executive.refetch()
    financialReturn.refetch()
    investor.refetch()
  }
  // Combinado dos 2 recursos — usado pelo `disabled`/texto "Atualizando..."
  // do `RefreshBar`.
  const loading =
    executive.status === 'loading' || financialReturn.status === 'loading' || investor.status === 'loading'

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
      <PageHeader
        eyebrow="Painel financeiro"
        title="Financeiro"
        description="Leitura do ciclo, créditos de energia e retorno do investimento em uma visão preparada para decisão."
        headingRef={headingRef}
        actions={<RefreshBar onRefresh={refreshAll} loading={loading} className="mb-0 lg:justify-self-end" />}
      />
      {/* Faturas primeiro: sem fatura confirmada não existe custo do ciclo,
          economia nem retorno — é a porta de entrada dos dados financeiros.
          Fica fora do bloco do recurso executivo para continuar disponível
          mesmo quando ele falha ou ainda não tem ciclo nenhum. */}
      <BillsSection plantId={plantId} onConfirmed={refreshAll} />
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
          <Suspense
            fallback={
              <div
                className="h-40 animate-pulse rounded-[var(--radius-card)] bg-[var(--color-surface-subtle)] md:col-span-6 lg:col-span-12"
                aria-hidden="true"
              />
            }
          >
            <InvestorPanelSection panel={investor.data} error={investor.error} onRetry={investor.refetch} />
          </Suspense>
        </div>
      )}
    </>
  )
}
