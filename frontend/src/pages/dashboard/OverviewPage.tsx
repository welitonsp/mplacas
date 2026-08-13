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
import { StackedBar } from '../../components/charts/StackedBar'
import { HeroCard } from '../../components/HeroCard'
import { QualityBanner } from '../../components/QualityBanner'
import { TrendCard } from '../../components/TrendCard'
import { EnergyFlowDiagram } from '../../components/EnergyFlowDiagram'
import { DiagnosticsCard } from '../../components/DiagnosticsCard'
import { EmptyState } from '../../components/EmptyState'
import { hasIncompleteDailyProduction } from '../../components/EnergyProductionSection'
import { MetricCard } from '../../components/MetricCard'
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
        className="md:col-span-6 lg:col-span-12"
      >
        <div className="rounded-3xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-sm">
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
        className="md:col-span-6 lg:col-span-12"
      >
        <div className="rounded-3xl border border-gray-200 bg-gray-50 p-5 text-gray-700 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-brand-primary)]">
            Indicador chave
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-gray-950">
            Produção e Saúde da Usina
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
  const latestPoint = [...recent].reverse().find((day) => toNumber(day.actual_production_kwh) != null) ?? null
  const latestActual = latestPoint ? toNumber(latestPoint.actual_production_kwh) : null
  const maxBar = Math.max(
    ...recent.map((day) => toNumber(day.actual_production_kwh) ?? 0),
    ...recent.map((day) => toNumber(day.expected_production_kwh) ?? 0),
    1,
  )

  return (
    <section
      data-testid="production-health-hero"
      aria-label="Produção e saúde da usina"
      className="md:col-span-6 lg:col-span-12"
    >
      <div className="overflow-hidden rounded-3xl border border-[var(--color-brand-primary)]/20 bg-[linear-gradient(135deg,var(--color-surface)_0%,var(--color-brand-primary-light)_100%)] shadow-[0_18px_50px_-28px_rgba(37,99,235,0.55)]">
        <div className="grid gap-6 p-5 md:p-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(18rem,0.95fr)] lg:items-end">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-brand-primary)]">
                Indicador chave
              </p>
              <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${PRODUCTION_HEALTH_CLASSES[alertSignal.tone]}`}>
                {alertSignal.label}
              </span>
              <span
                data-testid="production-health-confidence-badge"
                className={`rounded-full border px-3 py-1 text-xs font-semibold ${PRODUCTION_HEALTH_CLASSES[confidence.tone]}`}
              >
                {confidence.label} · ciclo {referenceMonth}
              </span>
            </div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-gray-950 md:text-3xl">
              Produção e Saúde da Usina
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-700">
              {alertSignal.detail} Este é o primeiro sinal operacional: mostra se a usina está gerando dentro do esperado nos últimos 7 dias.
            </p>
            <div
              data-testid="production-health-action"
              className={`mt-4 max-w-3xl rounded-2xl border px-3 py-3 ${PRODUCTION_HEALTH_CLASSES[alertSignal.tone]}`}
            >
              <p className="text-xs font-semibold uppercase tracking-[0.14em] opacity-80">Próxima ação</p>
              <p className="mt-1 text-base font-semibold">{action.title}</p>
              <p className="mt-1 text-sm leading-6 opacity-85">{action.detail}</p>
            </div>
            <Link
              to={DASHBOARD_PRODUCTION_PATH}
              className="mt-4 inline-flex min-h-[44px] items-center rounded-full bg-[var(--color-brand-primary)] px-4 text-sm font-semibold text-white shadow-sm transition-transform hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 motion-reduce:transition-none"
            >
              Abrir análise completa <span aria-hidden="true" className="ml-1">→</span>
            </Link>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-2xl border border-white/70 bg-white/80 px-3 py-3 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Último dia</p>
              <p className="mt-1 text-2xl font-semibold text-gray-950 tabular-nums">
                {latestActual == null ? '—' : `${formatNumber(latestActual, 1)} kWh`}
              </p>
              <p className="mt-1 text-xs text-gray-500">
                {latestPoint ? formatShortDate(latestPoint.date) : 'sem dado diário'}
              </p>
            </div>
            <div className="rounded-2xl border border-white/70 bg-white/80 px-3 py-3 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Média 7 dias</p>
              <p className="mt-1 text-2xl font-semibold text-gray-950 tabular-nums">
                {average.average == null ? '—' : `${formatNumber(average.average, 1)} kWh/dia`}
              </p>
              <p className="mt-1 text-xs text-gray-500">
                {average.days} {average.days === 1 ? 'dia com dado' : 'dias com dado'}
              </p>
            </div>
            <div className="rounded-2xl border border-white/70 bg-white/80 px-3 py-3 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Desempenho vs esperado</p>
              <p className="mt-1 text-2xl font-semibold text-gray-950 tabular-nums">
                {performance.percent == null ? '—' : `${formatNumber(performance.percent, 1)}%`}
              </p>
              <p className="mt-1 text-xs text-gray-500">
                {performance.assessedDays > 0 ? `${performance.assessedDays} dias avaliados` : 'sem baseline no recorte'}
              </p>
            </div>
            <div className="rounded-2xl border border-white/70 bg-white/80 px-3 py-3 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Total 7 dias</p>
              <p className="mt-1 text-2xl font-semibold text-gray-950 tabular-nums">
                {productionValues.length === 0 ? '—' : `${formatNumber(totalProduction, 1)} kWh`}
              </p>
              <p className="mt-1 text-xs text-gray-500">produção acumulada recente</p>
            </div>
          </div>
        </div>

        <div className="border-t border-white/70 bg-white/55 px-5 py-4 md:px-6">
          <div className="flex h-24 items-end gap-2" aria-label="Mini gráfico dos últimos 7 dias">
            {recent.map((day) => {
              const actual = toNumber(day.actual_production_kwh) ?? 0
              const expected = toNumber(day.expected_production_kwh)
              const severity = levelSeverity(day.level)
              const actualHeight = Math.max(6, Math.min(100, (actual / maxBar) * 100))
              const expectedHeight = expected == null ? null : Math.max(6, Math.min(100, (expected / maxBar) * 100))

              return (
                <div
                  key={day.date}
                  className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1"
                  aria-label={`${formatShortDate(day.date)}: ${formatNumber(actual, 1)} kWh, ${levelLabel(day.level)}`}
                >
                  <div className="relative flex h-full w-full max-w-12 items-end justify-center">
                    {expectedHeight != null && (
                      <span
                        className="absolute bottom-0 w-full rounded-t-md border-t-2 border-dashed border-[var(--color-chart-reference)]"
                        style={{ height: `${expectedHeight}%` }}
                        aria-hidden="true"
                      />
                    )}
                    <span
                      data-testid="production-health-mini-bar"
                      data-severity={severity}
                      className={`relative z-10 w-full max-w-8 rounded-t-lg ${SEVERITY_BAR[severity]}`}
                      style={{ height: `${actualHeight}%` }}
                      aria-hidden="true"
                    />
                  </div>
                  <span className="text-xs font-semibold text-gray-600 tabular-nums">{formatShortDate(day.date)}</span>
                </div>
              )
            })}
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
        eyebrow="Cockpit"
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
          <div className="grid grid-cols-1 gap-4 md:grid-cols-6 lg:grid-cols-12 lg:gap-6 items-start">
            <ProductionHealthHero
              anomalyData={anomalies.data}
              loading={anomalies.status === 'loading'}
              error={anomalies.error}
              quality={quality}
              latestDataDate={latestDataDate}
              referenceMonth={data.current_cycle.reference_month}
            />

            {buildDataConfidenceSummary(quality, latestDataDate).tone !== 'success' && (
              <section className="md:col-span-6 lg:col-span-12" aria-label="Confiança dos dados do ciclo">
                <DataConfidenceStrip
                  quality={quality}
                  latestDataDate={latestDataDate}
                  referenceMonth={data.current_cycle.reference_month}
                />
              </section>
            )}

            <section className="md:col-span-6 lg:col-span-12" aria-label="Decisão executiva do ciclo">
              <ExecutiveDecisionPanel
                dashboard={data}
                diagnostics={diagnostics}
                latestProduction={latestProduction}
                latestDataDate={latestDataDate}
              />
            </section>

            {/* Faixa de estado — o hero de fato da página (diagnóstico de UX
                aprovado pelo usuário): une "está indo bem?" (`HeroCard`, saúde
                da usina) e "para onde foi a energia?" (`EnergyFlowDiagram`)
                numa única superfície com fundo de marca, full-width, acima da
                dobra. Ordem de leitura preservada — estado à esquerda, fluxo à
                direita, exatamente como as duas perguntas se sucedem. Fundo
                `--color-brand-primary-light` é só SUPERFÍCIE de estrutura
                (nunca codifica severidade de dado — isso continua vindo
                inteiramente de `SEVERITY_*`/`accent` do `HeroCard`/badges
                dentro dela); funciona nos dois temas sem token novo (ADR-071:
                `#eff6ff` claro / `#132038` escuro). */}
            <section
              data-testid="hero-band"
              aria-label="Resumo executivo da usina"
              className="overview-cockpit md:col-span-6 lg:col-span-12 overflow-hidden rounded-3xl border border-[var(--color-border)] bg-[var(--color-brand-primary-light)]"
            >
              <div className="grid grid-cols-1 gap-7 p-6 md:p-8 lg:grid-cols-12 lg:items-start">
                {/* Estado — ~5/12 em telas largas (`lg:`), primeiro no DOM
                    (também primeiro em mobile, onde a faixa empilha). */}
                <div className="lg:col-span-5 lg:border-r lg:border-[var(--color-border)] lg:pr-8">
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

                {/* Fluxo — ~7/12 em telas largas. Único diagrama de fluxo
                    (autoconsumo/injetada/importada não se repetem em mais
                    visuais) + o resumo proporcional dos mesmos fluxos logo
                    abaixo (StackedBar de autossuficiência/dependência da
                    rede). */}
                <div className="lg:col-span-7">
                  {/* "— ciclo {referenceMonth}" (achado A2 do audit de honestidade
                      de dado): o rótulo interno "Fluxo de energia no ciclo" foi
                      removido de `EnergyFlowDiagram` por duplicar este `<h2>`
                      externo, mas isso também removeu a única menção a "ciclo" da
                      faixa hero — sem ela nada aqui deixa claro que o diagrama é
                      do CICLO DE FATURAMENTO FECHADO, não de tempo real (ao
                      contrário do que produtos concorrentes como SolarEdge/
                      Enphase/Tesla costumam mostrar num diagrama de fluxo em
                      destaque). Carimbar o período no título resolve isso sem
                      reintroduzir a duplicação — mesmo tratamento no `h3` de
                      "Origem do consumo" logo abaixo (achado A3). */}
                  <SectionTitle as="h2">{`Fluxo de energia — ciclo ${data.current_cycle.reference_month}`}</SectionTitle>
                  <EnergyFlowDiagram
                    production={indicators.cycle_production_kwh}
                    selfConsumption={indicators.estimated_self_consumption_kwh}
                    injected={indicators.injected_kwh}
                    imported={indicators.imported_kwh}
                    consumption={indicators.estimated_total_consumption_kwh}
                    partial={hasIncompleteDailyProduction(quality)}
                    embedded
                  />

                  {/* A barra resume a origem do consumo. Quando uma das duas
                      parcelas está ausente, preservamos os cards separados
                      para não fabricar uma composição de 100%. */}
                  <div className="mt-4">
                    {selfSufficiencyPercent != null && gridDependencyPercent != null ? (
                      <div className="border-t border-[var(--color-border)] pt-4">
                        <SectionTitle as="h3">{`Origem do consumo — ciclo ${data.current_cycle.reference_month}`}</SectionTitle>
                        <StackedBar
                          segments={[
                            // Composição do consumo (de onde a energia veio), não
                            // severidade — autossuficiência alta não é "boa" nem
                            // dependência da rede é "ruim" no sentido de
                            // bom/ruim, é só como o total se distribuiu (achado M3
                            // do audit; mesmo raciocínio do fluxo em
                            // `EnergyFlowDiagram`). Os dois segmentos usam tom
                            // neutro — `tone: 'success'` era usado aqui por
                            // engano em "Autossuficiência".
                            { label: 'Autossuficiência', value: selfSufficiencyPercent, tone: 'neutral' },
                            { label: 'Dependência da rede', value: gridDependencyPercent, tone: 'neutral' },
                          ]}
                          total={100}
                          valueFormatter={(value) => `${formatNumber(value, 1)}%`}
                        />
                      </div>
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
                  </div>
                </div>
              </div>
              <OverviewKpiRail
                cycleProduction={indicators.cycle_production_kwh}
                latestProduction={latestProduction}
                latestProductionDate={latestDataDate}
                estimatedSavings={indicators.estimated_savings_brl}
                savingsUnavailableReason={indicators.savings_unavailable_reason}
                referenceMonth={data.current_cycle.reference_month}
              />
            </section>

            {/* O chip de atenção do cockpit aponta para esta seção. Quando há
                tendência, diagnóstico e evolução formam duas colunas; sem
                comparação disponível, o diagnóstico mantém largura de leitura. */}
            <section id="diagnosticos" className="md:col-span-6 lg:col-span-12">
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

            {/* "Energia e produção" (importada/injetada/autoconsumo/consumo)
                foi removida da composição — os mesmos quatro números já
                aparecem em "Fluxo de energia" (`EnergyFlowDiagram`), com a
                relação entre eles, que os cards isolados não davam. O
                componente `EnergyProductionSection` continua existindo em
                `components/` para reuso futuro, só não compõe mais este
                módulo. */}

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
