import { useMemo, useRef } from 'react'
import { fetchAnomalyHistory, fetchExecutiveDashboard, fetchFinancialReturn, fetchPlantSetup } from '../../lib/api'
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
import { parseFinancialReturn } from '../../lib/dashboard/financial-return-contracts'
import { parsePlantSetup } from '../../lib/dashboard/plant-setup-contracts'
import {
  buildCalmNote,
  buildHomeStatus,
  buildHomeTodos,
  buildUnavailableHomeStatus,
  buildWeekWindow,
} from '../../lib/dashboard/home'
import { formatCycleLabel } from '../../lib/format'
import { useModuleTitle } from '../../hooks/useModuleTitle'
import { SectionTitle } from '../../components/SectionTitle'
import { TrendCard } from '../../components/TrendCard'
import { hasIncompleteDailyProduction } from '../../components/EnergyProductionSection'
import { DiagnosticsCard } from '../../components/DiagnosticsCard'
import { EmptyState } from '../../components/EmptyState'
import { MetricCardSkeletonGrid } from '../../components/MetricCardSkeletonGrid'
import { RefreshBar } from '../../components/RefreshBar'
import { RetryableError } from '../../components/RetryableError'
import { PageHeader } from '../../components/PageHeader'
import { HomeStatusCard } from '../../components/home/HomeStatusCard'
import { HomeSavingsCard } from '../../components/home/HomeSavingsCard'
import { HomeWeekCard } from '../../components/home/HomeWeekCard'
import { HomeTodoList } from '../../components/home/HomeTodoList'

// Aba Início (ADR-083) — responde "está tudo bem?" em uma tela de celular:
// 1. uma frase de situação (telemetria recente + gatilho de produção);
// 2. quanto economizou no último ciclo com fatura e quanto do investimento
//    já voltou;
// 3. a produção dos últimos 7 dias;
// 4. "Precisa de você": só tarefas com ação concreta.
// O fluxo de energia, o desempenho e a decisão financeira moram nas abas
// Energia e Dinheiro; a lista completa de diagnósticos e a evolução do ciclo
// ficam recolhidas no fim, para quem quiser abrir.
//
// Quatro recursos, todos de leitura: executivo, produção diária, retorno do
// investimento e cadastro da usina (para tarefas pendentes). Falha dos dois
// últimos não derruba a tela: o cartão correspondente só omite a parte.
export function OverviewPage() {
  const { plantId, plants, loading: plantsLoading, error: plantsError } = usePlant()
  // `document.title`/foco por rota (ADR-072, Etapa 6) — ver `useModuleTitle`.
  // Chamado antes de qualquer `return` condicional abaixo (regra dos hooks).
  const headingRef = useModuleTitle('Início')

  const executive = usePlantResource({
    plantId,
    fetcher: fetchExecutiveDashboard,
    parse: parseExecutiveDashboard,
    errorMessage: 'Erro ao buscar dados.',
  })
  const anomalies = usePlantResource<AnomalyDashboardResponse, AnomalyFetchError>({
    plantId,
    fetcher: fetchAnomalyHistory,
    parse: parseAnomalyDashboard,
    classifyError: (failure) =>
      failure.kind === 'http' ? classifyAnomalyErrorStatus(failure.status) : 'SERVER_ERROR',
  })
  const financialReturn = usePlantResource({
    plantId,
    fetcher: fetchFinancialReturn,
    parse: parseFinancialReturn,
    errorMessage: 'Erro ao buscar retorno do investimento.',
  })
  const setup = usePlantResource({
    plantId,
    fetcher: fetchPlantSetup,
    parse: parsePlantSetup,
    errorMessage: 'Erro ao buscar o cadastro da usina.',
  })

  const refreshAll = () => {
    executive.refetch()
    anomalies.refetch()
    financialReturn.refetch()
    setup.refetch()
  }
  const loading = [executive, anomalies, financialReturn, setup].some((resource) => resource.status === 'loading')

  const data = executive.data
  const daily = anomalies.data?.daily ?? null
  const latestDataDate = daily ? latestNonNullProductionDate(daily) : null
  const diagnostics = useMemo(() => (data ? combineDiagnostics(data) : []), [data])
  // Histórico diário com erro (inclusive 404: nenhuma produção em 90 dias)
  // vira uma frase de situação explícita — nunca some em silêncio.
  const status = daily
    ? buildHomeStatus({ daily, latestDataDate, today: new Date() })
    : anomalies.error
      ? buildUnavailableHomeStatus(anomalies.error)
      : null
  const week = daily ? buildWeekWindow(daily, latestDataDate) : []
  const todos = buildHomeTodos({ setup: setup.data, diagnostics })
  const setupStatus = setup.data ? 'ready' : setup.error ? 'error' : 'loading'

  // A tarefa de diagnóstico crítico abre a lista completa, recolhida no fim.
  const diagnosticsRef = useRef<HTMLDetailsElement>(null)
  const openDiagnostics = () => {
    const details = diagnosticsRef.current
    if (!details) return
    details.open = true
    details.scrollIntoView?.({ block: 'start' })
    details.querySelector('summary')?.focus()
  }

  if (plantsLoading) {
    return <MetricCardSkeletonGrid />
  }

  if (plantsError) {
    return <RetryableError message={plantsError} onRetry={() => window.location.reload()} className="mb-6" />
  }

  // Organização sem nenhuma usina cadastrada (`count == 0`, ADR-069, seção 7):
  // estado vazio explícito, zero chamadas de dados disparadas.
  if (!plantId || plants.length === 0) {
    return (
      <EmptyState
        eyebrow="Configuração inicial"
        title="Nenhuma usina cadastrada"
        description="Nenhuma usina cadastrada para esta conta ainda. Assim que uma usina for vinculada, o resumo dela aparecerá aqui."
        tone="brand"
      />
    )
  }

  const cycleLabel = data ? formatCycleLabel(data.current_cycle.reference_month) : null

  return (
    <>
      <PageHeader
        eyebrow="Sua usina"
        title="Início"
        description="Está tudo bem? O resumo do que importa, em uma tela."
        headingRef={headingRef}
        actions={<RefreshBar onRefresh={refreshAll} loading={loading} className="mb-0" />}
      />

      {executive.error && <RetryableError message={executive.error} onRetry={refreshAll} className="mb-6" />}

      <div className="flex flex-col gap-4 sm:gap-5">
        {status ? (
          <HomeStatusCard status={status} />
        ) : anomalies.status === 'loading' ? (
          <div className="h-[84px] animate-pulse rounded-[var(--radius-card)] bg-[var(--color-surface-sunken)]" aria-hidden="true" />
        ) : null}

        {executive.status === 'loading' && !data && <MetricCardSkeletonGrid />}

        <div className="grid gap-4 sm:gap-5 lg:grid-cols-2">
          {data && (
            <HomeSavingsCard
              indicators={data.current_cycle.indicators}
              referenceMonth={data.current_cycle.reference_month}
              financialReturn={financialReturn.data}
              partial={hasIncompleteDailyProduction(data.current_cycle.quality)}
            />
          )}
          {daily && week.length > 0 && <HomeWeekCard week={week} />}
        </div>

        {(data || setup.data) && (
          <HomeTodoList
            todos={todos}
            setupStatus={setupStatus}
            onOpenDiagnostics={openDiagnostics}
            calmNote={data && cycleLabel ? buildCalmNote(data.current_cycle.quality, cycleLabel) : null}
          />
        )}

        {data && (
          <details ref={diagnosticsRef} className="group rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-card)]">
            <summary className="flex min-h-[52px] cursor-pointer list-none items-center justify-between gap-3 rounded-[var(--radius-card)] px-5 text-sm font-semibold text-[var(--color-text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] [&::-webkit-details-marker]:hidden">
              {`Diagnósticos e evolução do ciclo ${cycleLabel}`}
              <span aria-hidden="true" className="text-[var(--color-gray-500)] transition-transform duration-150 group-open:rotate-90 motion-reduce:transition-none">
                ›
              </span>
            </summary>
            <div id="diagnosticos" className="flex flex-col gap-6 border-t border-[var(--color-border)] p-5">
              <div>
                <SectionTitle as="h2">Diagnósticos</SectionTitle>
                <DiagnosticsCard diagnostics={diagnostics} plantId={plantId} />
              </div>
              {data.trend && (
                <div>
                  <SectionTitle as="h2">Comparado ao ciclo anterior</SectionTitle>
                  <TrendCard trend={data.trend} />
                </div>
              )}
            </div>
          </details>
        )}
      </div>
    </>
  )
}
