import type { CycleQuality } from '../lib/dashboard/contracts'
import { formatFullDate } from '../lib/format'

type ConfidenceTone = 'success' | 'warning' | 'danger'

interface DataConfidenceSummary {
  tone: ConfidenceTone
  label: string
  headline: string
  description: string
  decisionGuidance: string
  nextCheck: string
}

function totalIssueDays(quality: CycleQuality): number {
  return quality.missing_days + quality.provisional_days + quality.incomplete_days + quality.unavailable_days
}

function issueParts(quality: CycleQuality): string[] {
  return [
    { value: quality.missing_days, label: 'sem leitura' },
    { value: quality.provisional_days, label: 'provisório' },
    { value: quality.incomplete_days, label: 'incompleto' },
    { value: quality.unavailable_days, label: 'indisponível' },
  ]
    .filter((item) => item.value > 0)
    .map((item) => `${item.value} dia${item.value > 1 ? 's' : ''} ${item.label}${item.value > 1 && item.label !== 'sem leitura' ? 's' : ''}`)
}

function formatLastDataDate(latestDataDate: string | null): string {
  return latestDataDate ? formatFullDate(latestDataDate) : 'Sem leitura diária'
}

export function buildDataConfidenceSummary(quality: CycleQuality, latestDataDate: string | null): DataConfidenceSummary {
  const issues = totalIssueDays(quality)
  const hasHardGap = quality.missing_days + quality.unavailable_days > 0

  if (issues === 0) {
    return {
      tone: 'success',
      label: 'Alta confiança',
      headline: 'Dados prontos para decisão',
      description: `Última leitura diária: ${formatLastDataDate(latestDataDate)}.`,
      decisionGuidance: 'Use os indicadores do ciclo para decisão executiva.',
      nextCheck: 'Rotina semanal',
    }
  }

  if (hasHardGap) {
    return {
      tone: 'danger',
      label: 'Validar telemetria',
      headline: 'Decisão exige confirmação dos dados',
      description: `${issueParts(quality).join(', ')} no ciclo.`,
      decisionGuidance: 'Priorize a recomposição das leituras antes de concluir causa raiz.',
      nextCheck: 'Checar hoje',
    }
  }

  return {
    tone: 'warning',
    label: 'Leitura parcial',
    headline: 'Decisão permitida com ressalva operacional',
    description: `${issueParts(quality).join(', ')} no ciclo.`,
    decisionGuidance: 'Compare com histórico antes de transformar o sinal em ação corretiva.',
    nextCheck: 'Revisar no próximo ciclo',
  }
}

const toneClasses: Record<ConfidenceTone, { dot: string; badge: string; panel: string }> = {
  success: {
    dot: 'bg-[var(--color-success)]',
    badge: 'border-[var(--color-success)]/25 bg-[var(--color-success-light)] text-[var(--color-success-text)]',
    panel: 'border-[var(--color-success)]/20',
  },
  warning: {
    dot: 'bg-[var(--color-warning)]',
    badge: 'border-[var(--color-warning)]/25 bg-[var(--color-warning-light)] text-[var(--color-warning-text)]',
    panel: 'border-[var(--color-warning)]/25',
  },
  danger: {
    dot: 'bg-[var(--color-danger)]',
    badge: 'border-[var(--color-danger)]/25 bg-[var(--color-danger-light)] text-[var(--color-danger-text)]',
    panel: 'border-[var(--color-danger)]/25',
  },
}

export function DataConfidenceStrip({
  quality,
  latestDataDate,
  referenceMonth,
}: {
  quality: CycleQuality
  latestDataDate: string | null
  referenceMonth: string
}) {
  const summary = buildDataConfidenceSummary(quality, latestDataDate)
  const classes = toneClasses[summary.tone]

  return (
    <aside
      aria-label="Confiança dos dados"
      className={`rounded-2xl border bg-[var(--color-surface)] p-4 shadow-sm ${classes.panel}`}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${classes.badge}`}
            >
              <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${classes.dot}`} />
              {summary.label}
            </span>
            <span className="text-xs font-medium text-[var(--color-text-secondary)]">
              Ciclo {referenceMonth}
            </span>
          </div>
          <h2 className="mt-2 text-base font-semibold text-[var(--color-text)]">{summary.headline}</h2>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{summary.description}</p>
        </div>

        <dl className="grid gap-3 sm:grid-cols-2 lg:min-w-[28rem]">
          <div className="rounded-xl bg-[var(--color-surface-subtle)] px-3 py-2.5">
            <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Diretriz
            </dt>
            <dd className="mt-1 text-sm font-semibold text-[var(--color-text)]">{summary.decisionGuidance}</dd>
          </div>
          <div className="rounded-xl bg-[var(--color-surface-subtle)] px-3 py-2.5">
            <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Próximo check
            </dt>
            <dd className="mt-1 text-sm font-semibold text-[var(--color-text)]">{summary.nextCheck}</dd>
          </div>
        </dl>
      </div>
    </aside>
  )
}
