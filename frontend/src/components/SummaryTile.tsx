import type { Severity } from '../lib/dashboard/contracts'
import { SEVERITY_BG, SEVERITY_TEXT } from '../lib/dashboard/visuals'

export type SummaryTileTone = Severity | 'brand'

const SUMMARY_TILE_TONE: Record<SummaryTileTone, { bar: string; bg: string; text: string }> = {
  brand: {
    bar: 'bg-[var(--color-brand-primary)]',
    bg: 'bg-[var(--color-brand-primary-light)]',
    text: 'text-[var(--color-brand-primary)]',
  },
  success: {
    bar: 'bg-[var(--color-success)]',
    bg: SEVERITY_BG.success,
    text: SEVERITY_TEXT.success,
  },
  warning: {
    bar: 'bg-[var(--color-warning)]',
    bg: SEVERITY_BG.warning,
    text: SEVERITY_TEXT.warning,
  },
  danger: {
    bar: 'bg-[var(--color-danger)]',
    bg: SEVERITY_BG.danger,
    text: SEVERITY_TEXT.danger,
  },
  neutral: {
    bar: 'bg-gray-300',
    bg: SEVERITY_BG.neutral,
    text: SEVERITY_TEXT.neutral,
  },
}

export function SummaryTile({
  label,
  value,
  supportingText,
  tone,
}: {
  label: string
  value: string
  supportingText: string
  tone: SummaryTileTone
}) {
  const meta = SUMMARY_TILE_TONE[tone]

  return (
    <article className="min-h-[7.5rem] rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 shadow-sm sm:min-h-[8.5rem] sm:p-4">
      <div className={`mb-3 h-1 w-10 rounded-full sm:mb-4 ${meta.bar}`} aria-hidden="true" />
      <div className="text-sm font-semibold text-gray-600">{label}</div>
      <div className="mt-2 text-xl font-bold tabular-nums tracking-tight text-gray-950 sm:text-2xl">{value}</div>
      <div className={`mt-3 inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${meta.bg} ${meta.text}`}>
        {supportingText}
      </div>
    </article>
  )
}
