import { fetchAnomalyHistory, fetchExecutiveDashboard } from '../../lib/api'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import type { AnomalyDashboardResponse, AnomalyFetchError } from '../../lib/dashboard/contracts'
import {
  classifyAnomalyErrorStatus,
  combineDiagnostics,
  latestNonNullProductionDate,
  parseAnomalyDashboard,
  parseExecutiveDashboard,
} from '../../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../../lib/format'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import { SectionTitle } from '../../components/SectionTitle'
import { StackedBar } from '../../components/charts/StackedBar'
import { HeroCard } from '../../components/HeroCard'
import { QualityBanner } from '../../components/QualityBanner'
import { TrendCard } from '../../components/TrendCard'
import { EnergyFlowDiagram } from '../../components/EnergyFlowDiagram'
import { DiagnosticsCard } from '../../components/DiagnosticsCard'
import { hasIncompleteDailyProduction } from '../../components/EnergyProductionSection'
import { MetricCard } from '../../components/MetricCard'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { RefreshBar } from '../../components/RefreshBar'
import { RetryableError } from '../../components/RetryableError'

// Módulo Visão Geral (ADR-072, Etapa 5) — dois recursos (ver ADR seção 2):
// `executive` (`/energy/executive/latest`) e `anomalies`
// (`/energy/anomalies/latest`, usado só para `latestDataDate`). Renderiza
// Hero+QualityBanner, EnergyFlowDiagram, StackedBar de indicadores
// percentuais, DiagnosticsCard e TrendCard — exatamente o conteúdo que
// restava em `DashboardPage.tsx` antes desta etapa (agora removido, ver ADR).
export function OverviewPage() {
  const { plantId, plants, loading: plantsLoading, error: plantsError } = usePlant()
  // `document.title`/foco por rota (ADR-072, Etapa 6) — ver `useModuleTitle`.
  // Chamado antes de qualquer `return` condicional abaixo (regra dos hooks).
  const headingRef = useModuleTitle('Visão Geral')
  // `null` (`.data`) = ainda carregando `/energy/executive/latest`. O hook
  // cobre a mesma proteção de race condition/troca de usina que o fetch
  // manual anterior fazia à mão. Erro de rede/servidor fica em
  // `executive.error` (mensagem fixa, sem sufixo de status HTTP — o detalhe
  // vai para o console via o próprio hook, mesma política de `anomalies`
  // abaixo).
  const executive = usePlantResource({
    plantId,
    fetcher: fetchExecutiveDashboard,
    parse: parseExecutiveDashboard,
    errorMessage: 'Erro ao buscar dados.',
  })
  // `null` (`.data`) = ainda carregando `/energy/anomalies/latest`. Desde a
  // mudança de contrato deste endpoint (200 sempre, campos por dia `null`
  // sem expectativa), este recurso NÃO depende de nenhum outro: é buscado
  // assim que há `plantId`. O único uso deste recurso neste módulo (Visão
  // Geral) é `latestDataDate`, consumido pelo `HeroCard` — o restante do que
  // `anomalies` alimentava (histórico diário, produção do último dia) mora em
  // `pages/dashboard/ProductionPage.tsx`, que tem sua própria instância deste
  // mesmo recurso. `classifyError` reusa `classifyAnomalyErrorStatus` (já
  // testado isoladamente em `contracts.test.ts`): 404 vira `'NOT_FOUND'`,
  // 5xx vira `'SERVER_ERROR'`, e 401 já volta `null` de dentro da própria
  // função — falha silenciosa, mesma política de antes (`apiFetch` já tentou
  // refresh; se falhou, o usuário está sendo deslogado, não há nada a
  // comunicar aqui). Falha de rede/contrato (`kind !== 'http'`) cai no mesmo
  // `'SERVER_ERROR'`, mesma categoria de "algo quebrou" que um 5xx no
  // comportamento anterior.
  const anomalies = usePlantResource<AnomalyDashboardResponse, AnomalyFetchError>({
    plantId,
    fetcher: fetchAnomalyHistory,
    parse: parseAnomalyDashboard,
    classifyError: (failure) =>
      failure.kind === 'http' ? classifyAnomalyErrorStatus(failure.status) : 'SERVER_ERROR',
  })

  // Refetch único para os 2 recursos deste módulo — usado tanto pelo botão
  // "Atualizar" quanto pelo `RetryableError` do erro global.
  const refreshAll = () => {
    executive.refetch()
    anomalies.refetch()
  }
  // Combinado dos 2 recursos — usado pelo `disabled`/texto "Atualizando..."
  // do botão "Atualizar".
  const loading = executive.status === 'loading' || anomalies.status === 'loading'

  const data = executive.data
  // Usado só pelo esqueleto de carregamento do bloco principal (linha
  // `{loading && !data && ...}` abaixo) — continua amarrado especificamente
  // ao recurso executivo, que é quem preenche `data`. Não confundir com
  // `loading` (combinado) usado pelo botão "Atualizar": os dois têm
  // propósitos diferentes e podem divergir (ex.: executivo já respondeu com
  // erro mas outro recurso ainda está em voo — o esqueleto não deve
  // reaparecer por cima do banner de erro global).
  const executiveLoading = executive.status === 'loading'
  const error = executive.error
  const lastUpdated = executive.lastUpdated
  const indicators = data?.current_cycle.indicators
  const quality = data?.current_cycle.quality
  // Autossuficiência e dependência da rede são complementares (somam 100%) —
  // convertidos uma única vez para alimentar a `StackedBar` unificada
  // (ver seção "Indicadores percentuais" abaixo).
  const selfSufficiencyPercent = toNumber(indicators?.self_sufficiency_rate_percent ?? null)
  const gridDependencyPercent = toNumber(indicators?.grid_dependency_rate_percent ?? null)
  const latestDataDate = anomalies.data ? latestNonNullProductionDate(anomalies.data.daily) : null
  // Calculado uma única vez e reusado pelo chip do Hero (`AttentionSummary`)
  // e pela lista completa (`DiagnosticsCard`) — mesma lista, duas
  // apresentações.
  const diagnostics = data ? combineDiagnostics(data) : []

  // Enquanto a lista de usinas (`PlantContext`) ainda carrega, nenhuma
  // requisição deste módulo foi disparada — mesmo esqueleto de carregamento
  // usado por `ProductionPage`/`FinancialPage`/`TechnicalPage` para o mesmo
  // estado.
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
      <div className="rounded-lg border border-gray-200 bg-[var(--color-surface)] px-6 py-10 text-center text-sm text-gray-600">
        Nenhuma usina cadastrada para esta conta ainda.
      </div>
    )
  }

  return (
    <>
      {/* `<h1>` próprio do módulo (ADR-072, Etapa 6) — alvo do foco/título por
          rota (`useModuleTitle`), essencial para leitor de tela perceber a
          troca de "página" entre os 4 módulos (navegação client-side não
          reseta o foco sozinha). `tabIndex={-1}`: focável via `.focus()`,
          fora da ordem normal de tabulação. A casca do app (`AppHeader`)
          identifica o produto, não a rota atual — por isso um heading por
          módulo deixou de ser redundante. */}
      <h1 ref={headingRef} tabIndex={-1} className="mb-1 text-xl font-bold text-gray-900 tracking-tight focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] rounded">
        Visão Geral
      </h1>
      <RefreshBar onRefresh={refreshAll} loading={loading} />

      {error && (
        // Retry associado diretamente ao erro global (não só o link
        // "Atualizar" no topo da página).
        <RetryableError
          message={error}
          onRetry={refreshAll}
          className="mb-6"
        />
      )}

      {executiveLoading && !data && <MetricCardSkeletonGrid />}

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

            {/* Bloco 2 — "Para onde foi a energia?": um único diagrama de
                fluxo (autoconsumo/injetada/importada não se repetem em mais
                visuais), detalhamento numérico e histórico. */}
            <section className="md:col-span-3 lg:col-span-7">
              <SectionTitle as="h2">Fluxo de energia</SectionTitle>
              <EnergyFlowDiagram
                production={indicators.cycle_production_kwh}
                selfConsumption={indicators.estimated_self_consumption_kwh}
                injected={indicators.injected_kwh}
                imported={indicators.imported_kwh}
                consumption={indicators.estimated_total_consumption_kwh}
                partial={hasIncompleteDailyProduction(quality)}
              />
            </section>

            {/* Diagnósticos e comparação com o ciclo anterior, empilhados na
                mesma coluna estreita. `id` é o alvo da âncora do chip de
                atenção no Hero (ver `AttentionSummary`). */}
            <section id="diagnosticos" className="md:col-span-3 lg:col-span-5">
              <DiagnosticsCard diagnostics={diagnostics} />

              {data.trend && (
                <div className="mt-8">
                  <SectionTitle as="h2">Tendência</SectionTitle>
                  <TrendCard trend={data.trend} />
                </div>
              )}
            </section>

            {/* "Energia e produção" (importada/injetada/autoconsumo/consumo)
                foi removida da composição — os mesmos quatro números já
                aparecem em "Fluxo de energia" (`EnergyFlowDiagram`), com a
                relação entre eles, que os cards isolados não davam. O
                componente `EnergyProductionSection` continua existindo em
                `components/` para reuso futuro, só não compõe mais este
                módulo. */}
            <section className="md:col-span-6 lg:col-span-12">
              <SectionTitle as="h2">Indicadores percentuais</SectionTitle>
              {/* Autossuficiência e dependência da rede são complementares
                  (somam 100%) — uma única `StackedBar` de 2 segmentos deixa a
                  proporção explícita. Se qualquer um dos dois vier `null`,
                  mantém os cards separados em vez de fabricar a barra com
                  metade do dado ausente. */}
              {selfSufficiencyPercent != null && gridDependencyPercent != null ? (
                <StackedBar
                  segments={[
                    { label: 'Autossuficiência', value: selfSufficiencyPercent, tone: 'success' },
                    { label: 'Dependência da rede', value: gridDependencyPercent, tone: 'neutral' },
                  ]}
                  total={100}
                  valueFormatter={(value) => `${formatNumber(value, 1)}%`}
                />
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <MetricCard
                    label="Autossuficiência"
                    value={indicators.self_sufficiency_rate_percent}
                    unit="%"
                    barPercent={selfSufficiencyPercent}
                  />
                  <MetricCard
                    label="Dependência da rede"
                    value={indicators.grid_dependency_rate_percent}
                    unit="%"
                    barPercent={gridDependencyPercent}
                  />
                </div>
              )}
            </section>

            {/* Bloco "Quanto produziu? Qual o histórico?" (produção por
                ciclo de faturamento, histórico diário e produção do último
                dia vs. esperada) mora no módulo próprio em
                `pages/dashboard/ProductionPage.tsx` (ADR-072, Etapa 4) — não
                aparece mais aqui, para não duplicar entre as rotas
                `/dashboard/producao` e esta. */}

            {/* Bloco "Quanto custou? Qual o retorno?" (financeiro completo:
                custo do ciclo, tarifas, créditos e retorno do investimento)
                mora no módulo próprio em `pages/dashboard/FinancialPage.tsx`
                (ADR-072, Etapa 3) — não aparece mais aqui, para não duplicar
                entre as rotas `/dashboard/financeiro` e esta. */}

            {/* O bloco "Como está o desempenho técnico?" (PR, yield
                específico, disponibilidade de reporte, degradação e
                atribuição de causa de perda) mora no módulo próprio em
                `pages/dashboard/TechnicalPage.tsx` (ADR-072, Etapa 2) — não
                aparece mais aqui, para não duplicar entre as rotas
                `/dashboard/tecnico` e esta. */}
          </div>
        )}
    </>
  )
}
