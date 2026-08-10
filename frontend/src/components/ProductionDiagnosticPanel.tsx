import type { AnomalyDashboardResponse, AnomalyDailyPoint, AnomalyFetchState, Severity } from '../lib/dashboard/contracts'
import { productionAlertSignal } from '../lib/dashboard/production-alerts'
import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'
import { baselineUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { levelLabel, levelSeverity, SEVERITY_BG, SEVERITY_TEXT } from '../lib/dashboard/visuals'
import { formatFullDate, formatNumber, toNumber } from '../lib/format'
import { Card } from './Card'
import { OperationalState } from './OperationalState'

interface ProductionDiagnosis {
  tone: Severity
  title: string
  confidence: 'Alta' | 'Média' | 'Baixa'
  window?: string
  owner?: string
  cause: string
  impact: string
  action: string
  evidenceSummary?: string
  playbook?: Array<{ title: string; detail: string }>
  signals: Array<{ label: string; value: string; tone: Severity }>
}

const LEVEL_RANK: Record<NonNullable<AnomalyDailyPoint['level']>, number> = {
  CRITICAL: 0,
  ANOMALY: 1,
  ATTENTION: 2,
  NORMAL: 3,
}

function formatKwh(value: number | null, maximumFractionDigits = 0): string {
  return value === null ? '—' : `${formatNumber(value, maximumFractionDigits)} kWh`
}

function formatDeviation(value: number | null): string {
  if (value === null) return '—'
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${formatNumber(value, 1)}%`
}

function actualDays(data: AnomalyDashboardResponse): AnomalyDailyPoint[] {
  return data.daily.filter((day) => toNumber(day.actual_production_kwh) !== null)
}

function assessedDays(data: AnomalyDashboardResponse): AnomalyDailyPoint[] {
  return data.daily.filter(
    (day) => toNumber(day.actual_production_kwh) !== null && toNumber(day.expected_production_kwh) !== null && day.level !== null,
  )
}

function underExpectedDays(data: AnomalyDashboardResponse): AnomalyDailyPoint[] {
  return assessedDays(data).filter((day) => (toNumber(day.deviation_percent) ?? 0) < 0)
}

function worstProductionDay(data: AnomalyDashboardResponse): AnomalyDailyPoint | null {
  const days = assessedDays(data)
  if (days.length === 0) return null

  return [...days].sort((left, right) => {
    const severityDelta = LEVEL_RANK[left.level as NonNullable<AnomalyDailyPoint['level']>] - LEVEL_RANK[right.level as NonNullable<AnomalyDailyPoint['level']>]
    if (severityDelta !== 0) return severityDelta
    return (toNumber(left.deviation_percent) ?? 0) - (toNumber(right.deviation_percent) ?? 0)
  })[0]
}

function periodPerformance(data: AnomalyDashboardResponse): number | null {
  const totals = assessedDays(data).reduce(
    (acc, day) => {
      const actual = toNumber(day.actual_production_kwh)
      const expected = toNumber(day.expected_production_kwh)
      if (actual === null || expected === null) return acc
      return { actual: acc.actual + actual, expected: acc.expected + expected }
    },
    { actual: 0, expected: 0 },
  )
  return totals.expected > 0 ? (totals.actual / totals.expected) * 100 : null
}

function estimatedLossKwh(day: AnomalyDailyPoint | null): number | null {
  if (day === null) return null
  const actual = toNumber(day.actual_production_kwh)
  const expected = toNumber(day.expected_production_kwh)
  if (actual === null || expected === null) return null
  return Math.max(expected - actual, 0)
}

function totalLossKwh(data: AnomalyDashboardResponse): number | null {
  const losses = underExpectedDays(data)
    .map(estimatedLossKwh)
    .filter((value): value is number => value !== null)
  if (losses.length === 0) return null
  return losses.reduce((sum, value) => sum + value, 0)
}

function buildSignals(data: AnomalyDashboardResponse | null): ProductionDiagnosis['signals'] {
  if (data === null) {
    return [
      { label: 'Pior dia', value: '—', tone: 'neutral' },
      { label: 'Perda estimada', value: '—', tone: 'neutral' },
      { label: 'Dias abaixo', value: '—', tone: 'neutral' },
      { label: 'Desempenho do período', value: '—', tone: 'neutral' },
    ]
  }

  const worstDay = worstProductionDay(data)
  const loss = estimatedLossKwh(worstDay)
  const totalLoss = totalLossKwh(data)
  const belowDays = underExpectedDays(data).length
  const performance = periodPerformance(data)
  const worstTone = worstDay ? levelSeverity(worstDay.level) : 'neutral'

  return [
    {
      label: 'Pior dia',
      value: worstDay ? `${formatFullDate(worstDay.date)} · ${formatDeviation(toNumber(worstDay.deviation_percent))}` : '—',
      tone: worstTone,
    },
    {
      label: 'Perda estimada',
      value: loss === null ? '—' : `${formatKwh(loss, 1)} no pior dia${totalLoss !== null ? ` · ${formatKwh(totalLoss, 1)} no período` : ''}`,
      tone: loss !== null && loss > 0 ? worstTone : 'neutral',
    },
    {
      label: 'Dias abaixo',
      value: `${belowDays} ${belowDays === 1 ? 'dia' : 'dias'}`,
      tone: belowDays > 0 ? 'warning' : 'success',
    },
    {
      label: 'Desempenho do período',
      value: performance === null ? '—' : `${formatNumber(performance, 1)}%`,
      tone: performance === null ? 'neutral' : performance < 70 ? 'danger' : performance < 85 ? 'warning' : 'success',
    },
  ]
}

function defaultWindow(tone: Severity): string {
  if (tone === 'danger') return 'Agir hoje'
  if (tone === 'warning') return 'Monitorar próximos dias'
  if (tone === 'success') return 'Rotina semanal'
  return 'Completar dados'
}

function defaultOwner(tone: Severity): string {
  if (tone === 'danger') return 'Operação + técnico'
  if (tone === 'warning') return 'Operação'
  if (tone === 'success') return 'Gestão operacional'
  return 'Operação'
}

function defaultPlaybook(tone: Severity): Array<{ title: string; detail: string }> {
  if (tone === 'danger') {
    return [
      { title: 'Confirmar desvio', detail: 'Validar sequência de queda e descartar falha de coleta.' },
      { title: 'Cruzar com Técnico', detail: 'Verificar PR, disponibilidade, perdas prováveis e clima.' },
      { title: 'Medir recuperação', detail: 'Comparar os próximos dias contra o esperado após a ação.' },
    ]
  }

  if (tone === 'warning') {
    return [
      { title: 'Acompanhar repetição', detail: 'Verificar se o desvio volta nos próximos dias de geração.' },
      { title: 'Separar clima de falha', detail: 'Comparar com histórico, irradiância e usinas equivalentes quando houver.' },
      { title: 'Escalar se persistir', detail: 'Abrir investigação técnica se a sequência ou perda em kWh aumentar.' },
    ]
  }

  if (tone === 'success') {
    return [
      { title: 'Manter referência', detail: 'Usar o período saudável como baseline operacional recente.' },
      { title: 'Preservar rotina', detail: 'Continuar acompanhando produção diária e sequência de atenção.' },
      { title: 'Registrar normalidade', detail: 'Guardar o período como comparação para futuras anomalias.' },
    ]
  }

  return [
    { title: 'Completar histórico', detail: 'Aguardar coleta diária ou backfill antes de classificar perda.' },
    { title: 'Validar baseline', detail: 'Confirmar se a produção esperada já pode ser calculada.' },
    { title: 'Reabrir diagnóstico', detail: 'Reavaliar quando houver real e esperado no mesmo período.' },
  ]
}

export function buildProductionDiagnosis({
  anomalyState,
  expectedProduction,
}: {
  anomalyState: AnomalyFetchState
  expectedProduction: ExpectedDailyProduction | null
}): ProductionDiagnosis {
  if (anomalyState.loading && !anomalyState.data) {
    return {
      tone: 'neutral',
      title: 'Montando diagnóstico de produção',
      confidence: 'Baixa',
      cause: 'Aguardando histórico diário e referência esperada.',
      impact: 'A interface evita classificar perda antes de receber os dados mínimos.',
      action: 'Aguarde a atualização ou use atualizar se a coleta demorar mais que o normal.',
      signals: buildSignals(null),
    }
  }

  if (anomalyState.error === 'SERVER_ERROR') {
    return {
      tone: 'danger',
      title: 'Diagnóstico indisponível',
      confidence: 'Baixa',
      cause: 'O histórico diário não carregou com sucesso.',
      impact: 'Não é seguro concluir perda, normalidade ou recorrência sem a série diária.',
      action: 'Tentar atualizar o histórico de produção antes de decidir ação operacional.',
      signals: buildSignals(null),
    }
  }

  if (anomalyState.error === 'NOT_FOUND' || !anomalyState.data || actualDays(anomalyState.data).length === 0) {
    return {
      tone: 'neutral',
      title: 'Sem produção diária coletada',
      confidence: 'Baixa',
      cause: 'Ainda não há dados diários suficientes para avaliar desvio.',
      impact: 'O acompanhamento deve esperar coleta/backfill para comparar real contra esperado.',
      action: 'Confirmar se a usina já está integrada e se a coleta diária foi executada.',
      signals: buildSignals(null),
    }
  }

  const data = anomalyState.data

  if (data.expected_unavailable_reason !== null) {
    return {
      tone: 'neutral',
      title: 'Produção real disponível, sem referência esperada',
      confidence: 'Média',
      cause: expectedProduction
        ? expectedProduction.available
          ? 'O histórico de anomalias não trouxe expectativa para o período analisado.'
          : baselineUnavailableMessage(expectedProduction.reason, expectedProduction.referenceCompleteOn)
        : 'A referência esperada ainda está carregando.',
      impact: 'A produção real pode ser acompanhada, mas ainda não dá para estimar perda contra baseline.',
      action: 'Completar baseline sazonal ou dados técnicos necessários antes de classificar perda.',
      signals: buildSignals(data),
    }
  }

  const worstDay = worstProductionDay(data)
  const loss = estimatedLossKwh(worstDay)
  const totalLoss = totalLossKwh(data)
  const streak = data.current_streak_days

  if (worstDay && worstDay.level !== 'NORMAL' && streak > 0) {
    const tone = levelSeverity(worstDay.level)
    return {
      tone,
      title: 'Diagnóstico: perda recorrente de produção',
      confidence: 'Alta',
      cause: `${streak} ${streak === 1 ? 'dia seguido' : 'dias seguidos'} abaixo do esperado; pior dia em ${formatFullDate(worstDay.date)} (${formatDeviation(toNumber(worstDay.deviation_percent))}).`,
      impact:
        totalLoss !== null
          ? `Perda estimada de ${formatKwh(totalLoss, 1)} no período analisado, sendo ${formatKwh(loss, 1)} no pior dia.`
          : 'Há recorrência de desvio, mas a perda em kWh não pôde ser estimada com segurança.',
      action: 'Priorizar investigação de campo e cruzar com Técnico para separar clima, sujeira, sombra, inversor ou falha de telemetria.',
      signals: buildSignals(data),
    }
  }

  if (worstDay && worstDay.level !== 'NORMAL') {
    return {
      tone: levelSeverity(worstDay.level),
      title: 'Diagnóstico: desvio pontual de produção',
      confidence: 'Média',
      cause: `O pior dia foi ${formatFullDate(worstDay.date)}, classificado como ${levelLabel(worstDay.level).toLowerCase()}.`,
      impact: loss !== null && loss > 0 ? `Perda estimada de ${formatKwh(loss, 1)} nesse dia.` : 'O impacto em kWh ainda é baixo ou não estimável.',
      action: 'Monitorar se o padrão se repete nos próximos dias antes de abrir ação corretiva.',
      signals: buildSignals(data),
    }
  }

  return {
    tone: 'success',
    title: 'Diagnóstico: produção dentro do esperado',
    confidence: 'Alta',
    cause: 'Não há desvio relevante no período analisado.',
    impact: 'A geração diária está aderente à referência disponível.',
    action: 'Manter acompanhamento e usar o período como base de comparação para futuras anomalias.',
    signals: buildSignals(data),
  }
}

export function ProductionDiagnosticPanel({
  anomalyState,
  expectedProduction,
}: {
  anomalyState: AnomalyFetchState
  expectedProduction: ExpectedDailyProduction | null
}) {
  const diagnosis = buildProductionDiagnosis({ anomalyState, expectedProduction })

  const shouldUseOperationalState =
    (anomalyState.loading && !anomalyState.data) ||
    anomalyState.error === 'SERVER_ERROR' ||
    anomalyState.error === 'NOT_FOUND' ||
    !anomalyState.data ||
    (anomalyState.data !== null && actualDays(anomalyState.data).length === 0) ||
    (anomalyState.data?.expected_unavailable_reason ?? null) !== null

  if (shouldUseOperationalState) {
    return (
      <OperationalState
        role={anomalyState.error === 'SERVER_ERROR' ? 'alert' : 'status'}
        tone={diagnosis.tone}
        icon={anomalyState.error === 'SERVER_ERROR' ? 'warning' : 'sync'}
        align="start"
        eyebrow="Diagnóstico de produção"
        title={diagnosis.title}
        description={diagnosis.cause}
        actionClassName="mt-5 space-y-4"
        action={
          <>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Impacto</p>
                <p className="mt-2 text-sm leading-6 text-gray-700">{diagnosis.impact}</p>
              </div>
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Próxima ação</p>
                <p className="mt-2 text-sm leading-6 text-gray-700">{diagnosis.action}</p>
              </div>
            </div>

            <div
              role="group"
              aria-label="Sinais do diagnóstico de produção"
              className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4"
            >
              {diagnosis.signals.map((signal) => (
                <div
                  key={signal.label}
                  className={`rounded-2xl border border-[var(--color-border)] ${SEVERITY_BG[signal.tone]} px-3 py-2`}
                >
                  <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{signal.label}</p>
                  <p className={`mt-1 text-sm font-semibold ${SEVERITY_TEXT[signal.tone]}`}>{signal.value}</p>
                </div>
              ))}
            </div>
          </>
        }
      />
    )
  }

  const window = diagnosis.window ?? defaultWindow(diagnosis.tone)
  const owner = diagnosis.owner ?? defaultOwner(diagnosis.tone)
  const evidenceSummary =
    diagnosis.evidenceSummary ??
    diagnosis.signals.map((signal) => `${signal.label}: ${signal.value}`).join(' · ')
  const playbook = diagnosis.playbook ?? defaultPlaybook(diagnosis.tone)
  const alertSignal = anomalyState.data ? productionAlertSignal(anomalyState.data.daily) : null

  return (
    <Card accent={diagnosis.tone} className="overflow-hidden">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.6fr)] lg:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Diagnóstico de produção</p>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${SEVERITY_BG[diagnosis.tone]} ${SEVERITY_TEXT[diagnosis.tone]}`}
            >
              Confiança {diagnosis.confidence.toLowerCase()}
            </span>
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
              {window}
            </span>
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
              {owner}
            </span>
          </div>

          <h2 className="mt-2 text-xl font-semibold tracking-tight text-gray-950">{diagnosis.title}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">{diagnosis.cause}</p>

          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Impacto</p>
              <p className="mt-2 text-sm leading-6 text-gray-700">{diagnosis.impact}</p>
            </div>
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Próxima ação</p>
              <p className="mt-2 text-sm leading-6 text-gray-700">{diagnosis.action}</p>
            </div>
          </div>
        </div>

        <div role="group" aria-label="Sinais do diagnóstico de produção" className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1">
          {diagnosis.signals.map((signal) => (
            <div
              key={signal.label}
              className={`rounded-2xl border border-[var(--color-border)] ${SEVERITY_BG[signal.tone]} px-3 py-2`}
            >
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{signal.label}</p>
              <p className={`mt-1 text-sm font-semibold ${SEVERITY_TEXT[signal.tone]}`}>{signal.value}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Evidências usadas</p>
            <p className="mt-1 text-sm leading-6 text-gray-700">{evidenceSummary}</p>
          </div>
          <p className="rounded-full bg-[var(--color-surface-subtle)] px-3 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
            Plano de produção
          </p>
        </div>

        {alertSignal && (
          <div className={`mt-4 rounded-xl border border-[var(--color-border)] ${SEVERITY_BG[alertSignal.tone]} p-3`}>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Critério de alerta</p>
            <p className={`mt-1 text-sm font-semibold ${SEVERITY_TEXT[alertSignal.tone]}`}>
              {alertSignal.label}
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">
              {alertSignal.detail} Regra: 7 dias contra esperado; sem baseline, 7 dias contra a janela anterior.
            </p>
          </div>
        )}

        <ol aria-label="Plano operacional de produção" className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
          {playbook.map((step, index) => (
            <li key={step.title} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-3">
              <div className="flex items-center gap-2">
                <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${SEVERITY_BG[diagnosis.tone]} ${SEVERITY_TEXT[diagnosis.tone]}`}>
                  {index + 1}
                </span>
                <p className="text-sm font-semibold text-[var(--color-text)]">{step.title}</p>
              </div>
              <p className="mt-2 text-xs leading-5 text-[var(--color-text-secondary)]">{step.detail}</p>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  )
}
