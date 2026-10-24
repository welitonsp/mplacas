import { lazy, Suspense, useEffect } from 'react'
import { useLocation } from 'react-router'
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

// Painel do investidor sob demanda: chunk próprio (gráfico de patrimônio +
// premissas), para não estourar o teto de 15 kB do módulo Financeiro.
// Faturas (importação em lote, confirmação, meses a recalcular) também em
// chunk próprio: o módulo já estava no teto de 15 kB.
const BillsSection = lazy(() =>
  import('../../components/BillsSection').then((module) => ({ default: module.BillsSection })),
)

const InvestorPanelSection = lazy(() =>
  import('../../components/InvestorPanelSection').then((module) => ({
    default: module.InvestorPanelSection,
  })),
)

// Aba Dinheiro (ADR-072, Etapa 3; reorganizada no ADR-083, etapa 2). Recursos:
// `executive` (conta do ciclo, tarifas, créditos — `current_cycle.indicators` e
// `reference_month`, que nomeia o ciclo dos números exibidos, achado F1),
// `financialReturn` (ROI/payback), `investor` (usina × CDI) e, dentro de
// `BillsSection`, faturas pendentes e meses a recalcular.
export function FinancialPage() {
  const { plantId, plants, loading: plantsLoading, error: plantsError } = usePlant()
  // `document.title`/foco por rota (ADR-072, Etapa 6) — ver `useModuleTitle`.
  // Chamado antes de qualquer `return` condicional abaixo (regra dos hooks).
  const headingRef = useModuleTitle('Dinheiro')

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
        eyebrow="Sua usina"
        title="Dinheiro"
        description="Quanto a usina já devolveu e quanto rende."
        headingRef={headingRef}
        actions={<RefreshBar onRefresh={refreshAll} loading={loading} className="mb-0 lg:justify-self-end" />}
      />
      {executive.error && (
        <RetryableError
          message={executive.error}
          onRetry={executive.refetch}
          className="mb-6"
        />
      )}

      {executiveLoading && !data && <MetricCardSkeletonGrid />}

      {data && indicators && (
        // Grade de 12 colunas: cada `<section>` de `FinancialSection` e o painel
        // do investidor ocupam uma linha cheia (`md:col-span-6 lg:col-span-12`).
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

      {/* Faturas sempre no fim e num ÚNICO ponto de montagem (ADR-083, etapa
          2). Mudar de lugar conforme o executivo carregava remontava a seção
          e apagava o retorno da importação, a lista de PDFs recusados e o
          foco (revisão da etapa 2). Usina sem ciclo não perde nada: acima
          delas só há o cabeçalho e o aviso do executivo. Fora do bloco do
          executivo, continuam disponíveis quando ele falha. */}
      <div id="faturas" className="mt-6 scroll-mt-4">
        <Suspense
          fallback={<div className="mb-6 h-40 animate-pulse rounded-[var(--radius-card)] bg-[var(--color-surface-subtle)]" aria-hidden="true" />}
        >
          <BillsSection plantId={plantId} onConfirmed={refreshAll} />
          <ScrollToBillsOnce />
        </Suspense>
      </div>
    </>
  )
}

// "Conferir faturas" no Início leva a `/dashboard/dinheiro#faturas`; o
// roteador não rola até a âncora sozinho. Montado junto de `BillsSection`
// (mesmo Suspense), rola UMA vez, quando as faturas já existem na tela — um
// "Atualizar" depois não puxa o usuário de volta para elas.
function ScrollToBillsOnce() {
  const location = useLocation()
  useEffect(() => {
    if (location.hash === '#faturas') {
      document.getElementById('faturas')?.scrollIntoView?.({ block: 'start' })
    }
    // Só na montagem: a rolagem é da chegada pelo link, não de cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return null
}
