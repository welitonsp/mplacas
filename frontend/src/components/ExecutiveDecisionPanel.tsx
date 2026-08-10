import type { Diagnostic, ExecutiveDashboardResponse, MetricValue, Severity } from '../lib/dashboard/contracts'
import { savingsUnavailableMessage } from '../lib/dashboard/contracts'
import { SEVERITY_BG, SEVERITY_TEXT, statusMeta } from '../lib/dashboard/visuals'
import { formatCurrency, formatFullDate, formatNumber, toNumber } from '../lib/format'
import { Card } from './Card'

interface ExecutiveDecision {
  tone: Severity
  eyebrow: string
  title: string
  summary: string
  impact: string
  action: string
  cadence: string
  owner: string
  playbook: Array<{ step: string; title: string; detail: string; tone: Severity }>
  signals: Array<{ label: string; value: string; tone: Severity }>
}

function diagnosticTone(diagnostic: Diagnostic | null, fallbackStatus: string): Severity {
  if (diagnostic?.severity === 'CRITICAL') return 'danger'
  if (diagnostic?.severity === 'WARNING') return 'warning'
  if (diagnostic?.severity === 'INFO') return 'neutral'
  return statusMeta(fallbackStatus).severity
}

function firstPriorityDiagnostic(diagnostics: Diagnostic[]): Diagnostic | null {
  return diagnostics[0] ?? null
}

function formatKwh(value: MetricValue, maximumFractionDigits = 0): string {
  return value == null ? '—' : `${formatNumber(value, maximumFractionDigits)} kWh`
}

function healthTone(healthScore: MetricValue): Severity {
  const score = toNumber(healthScore)
  if (score === null) return 'neutral'
  if (score < 70) return 'danger'
  if (score < 85) return 'warning'
  return 'success'
}

function savingsSignalValue(indicators: ExecutiveDashboardResponse['current_cycle']['indicators']): string {
  if (indicators.savings_unavailable_reason) {
    return savingsUnavailableMessage(indicators.savings_unavailable_reason)
  }
  return formatCurrency(indicators.estimated_savings_brl)
}

function buildDecisionPlaybook({
  tone,
  priority,
  recommendedAction,
}: {
  tone: Severity
  priority: Diagnostic | null
  recommendedAction: string
}): Pick<ExecutiveDecision, 'cadence' | 'owner' | 'playbook'> {
  if (tone === 'danger') {
    return {
      cadence: 'Agir nas próximas 24h',
      owner: 'Operação + técnico',
      playbook: [
        {
          step: '1',
          title: 'Confirmar telemetria',
          detail: 'Atualize os dados e valide se o desvio não vem de falha de coleta antes de acionar campo.',
          tone: 'neutral',
        },
        {
          step: '2',
          title: priority ? 'Atacar causa prioritária' : 'Isolar o desvio',
          detail: recommendedAction,
          tone: 'danger',
        },
        {
          step: '3',
          title: 'Registrar decisão',
          detail: 'Defina responsável, prazo e evidência esperada para fechar a ocorrência.',
          tone: 'warning',
        },
      ],
    }
  }

  if (tone === 'warning') {
    return {
      cadence: 'Revisar ainda hoje',
      owner: 'Operação',
      playbook: [
        {
          step: '1',
          title: 'Comparar com histórico',
          detail: 'Veja se o sinal aparece em produção, perdas ou qualidade dos dados antes de escalar.',
          tone: 'neutral',
        },
        {
          step: '2',
          title: priority ? 'Acompanhar alerta' : 'Validar tendência',
          detail: recommendedAction,
          tone: 'warning',
        },
        {
          step: '3',
          title: 'Revisar próximo ciclo',
          detail: 'Se repetir, trate como perda recorrente e abra análise técnica.',
          tone: 'neutral',
        },
      ],
    }
  }

  if (tone === 'success') {
    return {
      cadence: 'Manter rotina semanal',
      owner: 'Gestão operacional',
      playbook: [
        {
          step: '1',
          title: 'Usar como referência',
          detail: 'Compare os próximos ciclos contra este resultado para detectar desvios cedo.',
          tone: 'success',
        },
        {
          step: '2',
          title: 'Preservar qualidade',
          detail: 'Mantenha cadência de atualização e leitura dos indicadores-chave.',
          tone: 'neutral',
        },
        {
          step: '3',
          title: 'Registrar aprendizado',
          detail: recommendedAction,
          tone: 'neutral',
        },
      ],
    }
  }

  return {
    cadence: 'Monitorar na próxima leitura',
    owner: 'Operação',
    playbook: [
      {
        step: '1',
        title: 'Completar contexto',
        detail: 'Verifique se há dados suficientes antes de transformar o sinal em ação.',
        tone: 'neutral',
      },
      {
        step: '2',
        title: 'Acompanhar indicador',
        detail: recommendedAction,
        tone: 'neutral',
      },
      {
        step: '3',
        title: 'Reabrir se houver piora',
        detail: 'Se o status degradar, priorize investigação técnica e financeira.',
        tone: 'warning',
      },
    ],
  }
}

export function buildExecutiveDecision({
  dashboard,
  diagnostics,
  latestProduction,
  latestDataDate,
}: {
  dashboard: ExecutiveDashboardResponse
  diagnostics: Diagnostic[]
  latestProduction: MetricValue
  latestDataDate: string | null
}): ExecutiveDecision {
  const priority = firstPriorityDiagnostic(diagnostics)
  const tone = diagnosticTone(priority, dashboard.status)
  const indicators = dashboard.current_cycle.indicators
  const status = statusMeta(dashboard.status)
  const healthScore = toNumber(indicators.health_score)
  const hasSavingsUnavailable = indicators.savings_unavailable_reason !== null
  const formattedLatestDate = latestDataDate ? formatFullDate(latestDataDate) : null
  const savingsValue = savingsSignalValue(indicators)
  const signals: ExecutiveDecision['signals'] = [
    {
      label: 'Saúde',
      value: healthScore === null ? '—' : `${formatNumber(healthScore, 0)}/100`,
      tone: healthTone(indicators.health_score),
    },
    {
      label: 'Produção do ciclo',
      value: formatKwh(indicators.cycle_production_kwh),
      tone: 'neutral',
    },
    {
      label: formattedLatestDate ? `Último dia (${formattedLatestDate})` : 'Último dia',
      value: formatKwh(latestProduction),
      tone: 'neutral',
    },
    {
      label: 'Economia estimada',
      value: savingsValue,
      tone: hasSavingsUnavailable ? 'neutral' : 'success',
    },
  ]

  if (priority) {
    const severityLabel =
      priority.severity === 'CRITICAL'
        ? 'crítica'
        : priority.severity === 'WARNING'
          ? 'de atenção'
          : 'informativa'
    const action = priority.recommended_action
    return {
      tone,
      eyebrow: `Prioridade ${severityLabel}`,
      title: priority.message,
      summary: dashboard.headline,
      impact:
        priority.severity === 'CRITICAL'
          ? 'Risco relevante para geração, economia ou confiabilidade do ciclo. Trate antes de análises secundárias.'
          : priority.severity === 'WARNING'
            ? 'Há sinal de desvio que merece acompanhamento antes de virar perda recorrente.'
            : 'Existe contexto útil para melhorar a leitura executiva do ciclo.',
      action,
      ...buildDecisionPlaybook({ tone, priority, recommendedAction: action }),
      signals,
    }
  }

  if (status.severity === 'success') {
    const action = 'Manter monitoramento e usar este ciclo como referência para comparar desvios futuros.'
    return {
      tone: 'success',
      eyebrow: 'Decisão executiva',
      title: 'Operação sob controle',
      summary: dashboard.headline,
      impact: 'Sem alertas prioritários neste ciclo; os indicadores principais sustentam acompanhamento de rotina.',
      action,
      ...buildDecisionPlaybook({ tone: 'success', priority: null, recommendedAction: action }),
      signals,
    }
  }

  const action =
    dashboard.priority_actions[0] ?? 'Revisar indicadores do ciclo, qualidade dos dados e tendência antes de decidir ação de campo.'
  return {
    tone,
    eyebrow: 'Decisão executiva',
    title: status.severity === 'danger' ? 'Ciclo exige investigação' : 'Ciclo pede acompanhamento',
    summary: dashboard.headline,
    impact: 'O status executivo indica atenção, mesmo sem diagnóstico detalhado disponível no payload atual.',
    action,
    ...buildDecisionPlaybook({ tone, priority: null, recommendedAction: action }),
    signals,
  }
}

export function ExecutiveDecisionPanel({
  dashboard,
  diagnostics,
  latestProduction,
  latestDataDate,
}: {
  dashboard: ExecutiveDashboardResponse
  diagnostics: Diagnostic[]
  latestProduction: MetricValue
  latestDataDate: string | null
}) {
  const decision = buildExecutiveDecision({ dashboard, diagnostics, latestProduction, latestDataDate })

  return (
    <Card accent={decision.tone} className="overflow-hidden sm:p-6">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.55fr)] lg:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{decision.eyebrow}</p>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${SEVERITY_BG[decision.tone]} ${SEVERITY_TEXT[decision.tone]}`}
            >
              {decision.tone === 'danger'
                ? 'Resolver primeiro'
                : decision.tone === 'warning'
                  ? 'Acompanhar hoje'
                  : decision.tone === 'success'
                    ? 'Rotina'
                    : 'Monitorar'}
            </span>
          </div>

          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-gray-950">{decision.title}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">{decision.summary}</p>

          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Impacto</p>
              <p className="mt-2 text-sm leading-6 text-gray-700">{decision.impact}</p>
            </div>
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Próxima ação</p>
              <p className="mt-2 text-sm leading-6 text-gray-700">{decision.action}</p>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Janela de decisão</p>
              <p className="mt-1 text-sm font-semibold text-gray-950">{decision.cadence}</p>
            </div>
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Responsável sugerido</p>
              <p className="mt-1 text-sm font-semibold text-gray-950">{decision.owner}</p>
            </div>
          </div>
        </div>

        <div className="grid gap-3">
          <div role="group" aria-label="Sinais usados na decisão" className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1">
            {decision.signals.map((signal) => (
              <div
                key={signal.label}
                className={`rounded-2xl border border-[var(--color-border)] ${SEVERITY_BG[signal.tone]} px-3 py-2`}
              >
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{signal.label}</p>
                <p className={`mt-1 text-sm font-semibold ${SEVERITY_TEXT[signal.tone]}`}>{signal.value}</p>
              </div>
            ))}
          </div>

          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Plano de ação</p>
            <ol aria-label="Plano executivo de ação" className="mt-3 space-y-3">
              {decision.playbook.map((item) => (
                <li key={`${item.step}-${item.title}`} className="flex gap-3">
                  <span
                    aria-hidden="true"
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${SEVERITY_BG[item.tone]} ${SEVERITY_TEXT[item.tone]}`}
                  >
                    {item.step}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-gray-950">{item.title}</span>
                    <span className="mt-1 block text-xs leading-5 text-gray-600">{item.detail}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </Card>
  )
}
