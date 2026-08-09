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
      action: priority.recommended_action,
      signals,
    }
  }

  if (status.severity === 'success') {
    return {
      tone: 'success',
      eyebrow: 'Decisão executiva',
      title: 'Operação sob controle',
      summary: dashboard.headline,
      impact: 'Sem alertas prioritários neste ciclo; os indicadores principais sustentam acompanhamento de rotina.',
      action: 'Manter monitoramento e usar este ciclo como referência para comparar desvios futuros.',
      signals,
    }
  }

  return {
    tone,
    eyebrow: 'Decisão executiva',
    title: status.severity === 'danger' ? 'Ciclo exige investigação' : 'Ciclo pede acompanhamento',
    summary: dashboard.headline,
    impact: 'O status executivo indica atenção, mesmo sem diagnóstico detalhado disponível no payload atual.',
    action: dashboard.priority_actions[0] ?? 'Revisar indicadores do ciclo, qualidade dos dados e tendência antes de decidir ação de campo.',
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
        </div>

        <div role="group" aria-label="Sinais usados na decisão" className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1">
          {decision.signals.map((signal) => (
            <div
              key={signal.label}
              className={`rounded-2xl border border-[var(--color-border)] ${SEVERITY_BG[signal.tone]} px-3 py-2`}
            >
              <p className="text-[11px] font-medium uppercase tracking-wide text-gray-500">{signal.label}</p>
              <p className={`mt-1 text-sm font-semibold ${SEVERITY_TEXT[signal.tone]}`}>{signal.value}</p>
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}
