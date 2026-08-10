import type { CycleQuality } from '../lib/dashboard/contracts'
import { formatFullDate } from '../lib/format'
import { OperationalState, type OperationalStateIcon } from './OperationalState'

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

const confidenceIcon: Record<ConfidenceTone, OperationalStateIcon> = {
  success: 'check',
  warning: 'sync',
  danger: 'warning',
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

  return (
    <OperationalState
      role="complementary"
      ariaLabel="Confiança dos dados"
      tone={summary.tone}
      icon={confidenceIcon[summary.tone]}
      align="start"
      eyebrow={summary.label}
      title={summary.headline}
      description={summary.description}
      className="p-4"
      actionClassName="mt-5 space-y-3"
      action={
        <>
          <p className="text-xs font-medium text-[var(--color-text-secondary)]">
            Ciclo {referenceMonth}
          </p>
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
        </>
      }
    />
  )
}
