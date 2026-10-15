import { Link } from 'react-router'
import { fetchAnomalyHistory, fetchExecutiveDashboard } from '../../lib/api'
import { usePlant } from '../../contexts/PlantContext'
import { usePlantResource } from '../../hooks/usePlantResource'
import type { AnomalyDashboardResponse, AnomalyFetchError, CycleQuality, Severity } from '../../lib/dashboard/contracts'
import {
  classifyAnomalyErrorStatus,
  combineDiagnostics,
  latestNonNullProductionDate,
  parseAnomalyDashboard,
  parseExecutiveDashboard,
} from '../../lib/dashboard/contracts'
import {
  DEFAULT_PRODUCTION_PERIOD_DAYS,
  averageActualProduction,
  latestProductionDays,
  productionAlertSignal,
  productionPerformancePercent,
} from '../../lib/dashboard/production-alerts'
import { formatNumber, formatShortDate, toNumber } from '../../lib/format'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import { SectionTitle } from '../../components/SectionTitle'
import { HeroCard } from '../../components/HeroCard'
import { QualityBanner } from '../../components/QualityBanner'
import { TrendCard } from '../../components/TrendCard'
import { EnergyFlowDiagram } from '../../components/EnergyFlowDiagram'
import { DiagnosticsCard } from '../../components/DiagnosticsCard'
import { EmptyState } from '../../components/EmptyState'
import { hasIncompleteDailyProduction } from '../../components/EnergyProductionSection'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { RefreshBar } from '../../components/RefreshBar'
import { RetryableError } from '../../components/RetryableError'
import { OverviewKpiRail } from '../../components/OverviewKpiRail'
import { PageHeader } from '../../components/PageHeader'
import { ExecutiveDecisionPanel } from '../../components/ExecutiveDecisionPanel'
import { DataConfidenceStrip, buildDataConfidenceSummary } from '../../components/DataConfidenceStrip'
import { DASHBOARD_PRODUCTION_PATH } from '../../routes'
import { SEVERITY_BAR, levelLabel, levelSeverity } from '../../lib/dashboard/visuals'

const PRODUCTION_HEALTH_CLASSES: Record<Severity, string> = {
  success: 'border-[var(--color-success)]/25 bg-[var(--color-success-light)] text-[var(--color-success-text)]',
  warning: 'border-[var(--color-warning)]/30 bg-[var(--color-warning-light)] text-[var(--color-warning-text)]',
  danger: 'border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] text-[var(--color-danger-text)]',
  neutral: 'border-gray-200 bg-gray-50 text-gray-700',
}

function productionHealthAction(tone: Severity): { title: string; detail: string } {
  if (tone === 'danger') {
    return {
      title: 'Ação prioritária',
      detail: 'Verificar hoje inversor, comunicação, sujeira e sombreamento antes que a perda vire recorrente.',
    }
  }

  if (tone === 'warning') {
    return {
      title: 'Investigar se persistir',
      detail: 'Comparar com clima/irradiação e revisar operação se a queda continuar nos próximos dias.',
    }
  }

  if (tone === 'success') {
    return {
      title: 'Monitorar rotina',
      detail: 'Produção dentro do gatilho operacional. Manter acompanhamento diário e registrar desvios relevantes.',
    }
  }

  return {
    title: 'Coletar mais dados',
    detail: 'O gatilho precisa de pelo menos 3 dias avaliados para reduzir falso alerta operacional.',
  }
}

function ProductionHealthHero({
  anomalyData,
  loading,
  error,
  quality,
  latestDataDate,
  referenceMonth,
}: {
  anomalyData: AnomalyDashboardResponse | null
  loading: boolean
  error: AnomalyFetchError | null
  quality: CycleQuality
  latestDataDate: string | null
  referenceMonth: string
}) {
  if (loading && !anomalyData) {
    return (
      <section
        data-testid="production-health-hero"
        aria-label="Produção e saúde da usina"
      >
        <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-7">
          <div className="animate-pulse space-y-4">
            <div className="h-3 w-32 rounded bg-gray-200" />
            <div className="h-8 w-72 max-w-full rounded bg-gray-200" />
            <div className="grid gap-3 sm:grid-cols-4">
              <div className="h-20 rounded-2xl bg-gray-100" />
              <div className="h-20 rounded-2xl bg-gray-100" />
              <div className="h-20 rounded-2xl bg-gray-100" />
              <div className="h-20 rounded-2xl bg-gray-100" />
            </div>
          </div>
        </div>
      </section>
    )
  }

  if (!anomalyData || error) {
    const title = error === 'NOT_FOUND' ? 'Sem histórico diário ainda' : 'Produção diária indisponível'
    const detail =
      error === 'NOT_FOUND'
        ? 'Assim que a primeira coleta diária entrar, este será o indicador principal da usina.'
        : 'Não foi possível montar o indicador principal de produção agora. Use Atualizar para tentar novamente.'

    return (
      <section
        data-testid="production-health-hero"
        aria-label="Produção e saúde da usina"
      >
        <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-7">
          <p className="text-xs font-semibold text-[var(--color-brand-primary)]">
            Indicador chave
          </p>
          <h2 className="mt-2 text-[22px] font-semibold leading-tight text-[var(--color-text-primary)]">
            Produção dos últimos 7 dias
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">{title}. {detail}</p>
        </div>
      </section>
    )
  }

  const recent = latestProductionDays(anomalyData.daily, DEFAULT_PRODUCTION_PERIOD_DAYS)
  const alertSignal = productionAlertSignal(anomalyData.daily)
  const action = productionHealthAction(alertSignal.tone)
  const confidence = buildDataConfidenceSummary(quality, latestDataDate)
  const performance = productionPerformancePercent(recent)
  const average = averageActualProduction(recent)
  const productionValues = recent
    .map((day) => ({ day, actual: toNumber(day.actual_production_kwh) }))
    .filter((item): item is { day: NonNullable<typeof item.day>; actual: number } => item.actual != null)
  const totalProduction = productionValues.reduce((sum, item) => sum + item.actual, 0)
  const maxBar = Math.max(
    ...recent.map((day) => toNumber(day.actual_production_kwh) ?? 0),
    ...recent.map((day) => toNumber(day.expected_production_kwh) ?? 0),
    1,
  )

  // Cartão de produção recente (ADR-077, etapa 4). "Último dia" e
  // "Desempenho vs esperado" saíram daqui: estão na linha de indicadores logo
  // acima. Ficam o gráfico dos 7 dias, a média/total do recorte e a ação.
  return (
    <section data-testid="production-health-hero" aria-label="Produção e saúde da usina">
      <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">Indicador chave</p>
              <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${PRODUCTION_HEALTH_CLASSES[alertSignal.tone]}`}>
                {alertSignal.label}
              </span>
              <span
                data-testid="production-health-confidence-badge"
                className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${PRODUCTION_HEALTH_CLASSES[confidence.tone]}`}
              >
                {confidence.label} · ciclo {referenceMonth}
              </span>
            </div>
            <h2 className="mt-2 text-[22px] font-semibold leading-tight text-[var(--color-text-primary)]">
              Produção dos últimos 7 dias
            </h2>
            <p className="mt-1.5 max-w-2xl text-[15px] leading-6 text-[var(--color-text-secondary)]">{alertSignal.detail}</p>
          </div>
          <Link
            to={DASHBOARD_PRODUCTION_PATH}
            className="inline-flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-[var(--radius-control)] border border-[var(--color-border)] px-4 text-sm font-semibold text-[var(--color-text-primary)] transition-colors duration-150 hover:border-[var(--color-gray-300)] hover:bg-[var(--color-gray-50)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none"
          >
            Abrir análise completa <span aria-hidden="true">→</span>
          </Link>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(16rem,1fr)] lg:items-stretch">
          <div className="min-w-0">
            <div className="flex h-44 items-end gap-2 border-b border-[var(--color-gray-300)]" aria-label="Mini gráfico dos últimos 7 dias">
              {recent.map((day) => {
                const actualValue = toNumber(day.actual_production_kwh)
                const actual = actualValue ?? 0
                const expected = toNumber(day.expected_production_kwh)
                const severity = levelSeverity(day.level)
                const actualHeight = Math.max(4, Math.min(100, (actual / maxBar) * 100))
                const expectedHeight = expected == null ? null : Math.max(4, Math.min(100, (expected / maxBar) * 100))

                return (
                  <div
                    key={day.date}
                    className="relative flex h-full min-w-0 flex-1 flex-col items-center justify-end"
                    aria-label={`${formatShortDate(day.date)}: ${formatNumber(actual, 1)} kWh, ${levelLabel(day.level)}`}
                  >
                    {expectedHeight != null && (
                      <span
                        className="absolute inset-x-1 border-t-2 border-dashed border-[var(--color-chart-reference)]"
                        style={{ bottom: `calc(${expectedHeight}% * 0.82)` }}
                        aria-hidden="true"
                      />
                    )}
                    <span className="relative z-20 mb-1 rounded bg-[var(--color-surface)] px-1 text-xs font-semibold tabular-nums text-[var(--color-text-primary)]" aria-hidden="true">
                      {actualValue == null ? '—' : formatNumber(actualValue, 0)}
                    </span>
                    <span
                      data-testid="production-health-mini-bar"
                      data-severity={severity}
                      className={`relative z-10 w-full max-w-10 rounded-t-md ${SEVERITY_BAR[severity]}`}
                      style={{ height: `calc(${actualHeight}% * 0.82)` }}
                      aria-hidden="true"
                    />
                  </div>
                )
              })}
            </div>
            <div className="mt-1.5 flex gap-2" aria-hidden="true">
              {recent.map((day) => (
                <span key={day.date} className="min-w-0 flex-1 text-center text-xs tabular-nums text-[var(--color-text-secondary)]">
                  {formatShortDate(day.date)}
                </span>
              ))}
            </div>
            <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-[var(--color-text-secondary)]" aria-hidden="true">
              <span className="inline-flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-[3px] bg-[var(--color-success)]" />Produção medida
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="w-4 border-t-2 border-dashed border-[var(--color-chart-reference)]" />Esperado do dia
              </span>
            </p>
          </div>

          <div className="flex flex-col gap-4">
            <dl className="grid grid-cols-2 gap-4">
              <div>
                <dt className="text-[13px] font-medium text-[var(--color-text-secondary)]">Média 7 dias</dt>
                <dd className="mt-1 font-display text-[22px] font-semibold tabular-nums text-[var(--color-text-primary)]">
                  {average.average == null ? '—' : formatNumber(average.average, 1)}
                  {average.average != null && <span className="ml-1 font-sans text-sm font-medium text-[var(--color-text-secondary)]">kWh/dia</span>}
                </dd>
                <dd className="text-xs text-[var(--color-text-secondary)]">
                  {average.days} {average.days === 1 ? 'dia com dado' : 'dias com dado'}
                </dd>
              </div>
              <div>
                <dt className="text-[13px] font-medium text-[var(--color-text-secondary)]">Total 7 dias</dt>
                <dd className="mt-1 font-display text-[22px] font-semibold tabular-nums text-[var(--color-text-primary)]">
                  {productionValues.length === 0 ? '—' : formatNumber(totalProduction, 1)}
                  {productionValues.length > 0 && <span className="ml-1 font-sans text-sm font-medium text-[var(--color-text-secondary)]">kWh</span>}
                </dd>
                <dd className="text-xs text-[var(--color-text-secondary)]">
                  {performance.assessedDays > 0 ? `${performance.assessedDays} dias com esperado` : 'sem esperado no recorte'}
                </dd>
              </div>
            </dl>
            <div
              data-testid="production-health-action"
              className={`mt-auto rounded-2xl border px-4 py-3.5 ${PRODUCTION_HEALTH_CLASSES[alertSignal.tone]}`}
            >
              <p className="text-xs font-semibold opacity-85">Próxima ação</p>
              <p className="mt-0.5 text-[15px] font-semibold">{action.title}</p>
              <p className="mt-1 text-[13px] leading-5 opacity-90">{action.detail}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

// Módulo Visão Geral (ADR-072, Etapa 5) — dois recursos (ver ADR seção 2):
// `executive` (`/energy/executive/latest`) e `anomalies`
// (`/energy/anomalies/latest`, usado só para `latestDataDate`). Renderiza
// a faixa de estado em destaque (HeroCard+QualityBanner+EnergyFlowDiagram+
// StackedBar de indicadores percentuais, ver "faixa de estado" abaixo) e,
// abaixo dela, DiagnosticsCard e TrendCard — exatamente o conteúdo que
// restava em `DashboardPage.tsx` antes da Etapa 5 (agora removido, ver ADR),
// reorganizado para dar destaque visual ao diagrama de fluxo (diagnóstico de
// UX: o elemento que deveria ser o "hero" da tela estava enterrado como mais
// uma seção entre outras).
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
  const latestProduction = latestDataDate
    ? anomalies.data?.daily.find((point) => point.date === latestDataDate)?.actual_production_kwh ?? null
    : null
  // Calculado uma única vez e reusado pelo chip do Hero (`AttentionSummary`)
  // e pela lista completa (`DiagnosticsCard`) — mesma lista, duas
  // apresentações.
  const diagnostics = data ? combineDiagnostics(data) : []
  // Desempenho do recorte recente para o cartão "Desempenho vs esperado" —
  // mesmo cálculo que o cartão de produção usa, feito uma vez só.
  const recentPerformance = anomalies.data
    ? productionPerformancePercent(latestProductionDays(anomalies.data.daily, DEFAULT_PRODUCTION_PERIOD_DAYS))
    : { percent: null, assessedDays: 0 }

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
      <EmptyState
        eyebrow="Configuração inicial"
        title="Nenhuma usina cadastrada"
        description="Nenhuma usina cadastrada para esta conta ainda. Assim que uma usina for vinculada, o cockpit executivo aparecerá aqui."
        tone="brand"
      />
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
      <PageHeader
        eyebrow="Painel da usina"
        title="Visão Geral"
        description="Minha usina está bem hoje?"
        headingRef={headingRef}
        actions={<RefreshBar onRefresh={refreshAll} loading={loading} className="mb-0" />}
      />

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
        <div className="flex flex-col gap-5 sm:gap-6">
          {buildDataConfidenceSummary(quality, latestDataDate).tone !== 'success' && (
            <section aria-label="Confiança dos dados do ciclo">
              <DataConfidenceStrip
                quality={quality}
                latestDataDate={latestDataDate}
                referenceMonth={data.current_cycle.reference_month}
              />
            </section>
          )}

          {/* Resumo (ADR-077): estado da usina à esquerda, fluxo de energia à
              direita — as duas primeiras perguntas do dono, nesta ordem. */}
          <section
            data-testid="hero-band"
            aria-label="Resumo executivo da usina"
            className="overview-cockpit grid overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
          >
            <div className="p-5 sm:p-7">
              <HeroCard
                referenceMonth={data.current_cycle.reference_month}
                headline={data.headline}
                status={data.status}
                healthScore={indicators.health_score}
                latestDataDate={latestDataDate}
                lastSyncedAt={lastUpdated}
                diagnostics={diagnostics}
                embedded
              />
              <QualityBanner quality={quality} compact />
            </div>

            <div className="border-t border-[var(--color-border)] bg-[var(--color-surface-sunken)] p-5 sm:p-7 lg:border-l lg:border-t-0">
              {/* "— ciclo {mês}" (achado A2): deixa claro que é o ciclo de
                  faturamento fechado, não tempo real. */}
              <h2 className="text-base font-bold text-[var(--color-text-primary)]">
                {`Fluxo de energia — ciclo ${data.current_cycle.reference_month}`}
              </h2>
              <div className="mt-5">
                <EnergyFlowDiagram
                  production={indicators.cycle_production_kwh}
                  selfConsumption={indicators.estimated_self_consumption_kwh}
                  injected={indicators.injected_kwh}
                  imported={indicators.imported_kwh}
                  consumption={indicators.estimated_total_consumption_kwh}
                  partial={hasIncompleteDailyProduction(quality)}
                  embedded
                />
              </div>

              {/* Origem do consumo em percentual — dois números, não uma
                  terceira barra: a composição já está desenhada acima. Valor
                  ausente vira "—", nunca 0% nem 100% fabricado. */}
              <div role="group" aria-label={`Origem do consumo — ciclo ${data.current_cycle.reference_month}`}>
              <dl className="mt-6 grid grid-cols-2 gap-3">
                <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
                  <dt className="text-[13px] font-medium text-[var(--color-text-secondary)]">Autossuficiência</dt>
                  <dd className="mt-0.5 font-display text-[22px] font-semibold tabular-nums text-[var(--color-success-text)]">
                    {selfSufficiencyPercent == null ? '—' : `${formatNumber(selfSufficiencyPercent, 1)}%`}
                  </dd>
                </div>
                <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
                  <dt className="text-[13px] font-medium text-[var(--color-text-secondary)]">Dependência da rede</dt>
                  <dd className="mt-0.5 font-display text-[22px] font-semibold tabular-nums text-[var(--color-text-primary)]">
                    {gridDependencyPercent == null ? '—' : `${formatNumber(gridDependencyPercent, 1)}%`}
                  </dd>
                </div>
              </dl>
              </div>
            </div>
          </section>

          <OverviewKpiRail
            cycleProduction={indicators.cycle_production_kwh}
            latestProduction={latestProduction}
            latestProductionDate={latestDataDate}
            estimatedSavings={indicators.estimated_savings_brl}
            savingsUnavailableReason={indicators.savings_unavailable_reason}
            referenceMonth={data.current_cycle.reference_month}
            performancePercent={recentPerformance.percent}
            performanceAssessedDays={recentPerformance.assessedDays}
          />

          <ProductionHealthHero
            anomalyData={anomalies.data}
            loading={anomalies.status === 'loading'}
            error={anomalies.error}
            quality={quality}
            latestDataDate={latestDataDate}
            referenceMonth={data.current_cycle.reference_month}
          />

          <section aria-label="Decisão executiva do ciclo">
            <ExecutiveDecisionPanel
              dashboard={data}
              diagnostics={diagnostics}
              latestProduction={latestProduction}
              latestDataDate={latestDataDate}
            />
          </section>

          {/* O chip de atenção do resumo aponta para esta seção. */}
          <section id="diagnosticos">
            <div className={`grid gap-6 ${data.trend ? 'lg:grid-cols-[minmax(0,1.2fr)_minmax(20rem,0.8fr)]' : ''}`}>
              <div className={data.trend ? '' : 'lg:max-w-3xl'}>
                <SectionTitle as="h2">Atenção e próximos passos</SectionTitle>
                <DiagnosticsCard diagnostics={diagnostics} plantId={plantId} />
              </div>

              {data.trend && (
                <div>
                  <SectionTitle as="h2">Evolução do ciclo</SectionTitle>
                  <TrendCard trend={data.trend} />
                </div>
              )}
            </div>
          </section>

          {/* Produção por ciclo, financeiro completo e desempenho técnico
              moram nos módulos próprios (ADR-072) — não se repetem aqui. */}
        </div>
      )}
    </>
  )
}
