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
    bar: 'bg-[var(--color-gray-300)]',
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

  // Mesmo desenho dos indicadores da Visão Geral (ADR-077): rótulo, número em
  // destaque, contexto num selo. Sai o traço colorido no topo — a cor de
  // estado já está no selo, junto do texto que a explica.
  return (
    <article className="flex min-w-0 flex-col rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-[var(--shadow-card)] sm:p-5">
      <div className="text-[13px] font-medium leading-5 text-[var(--color-text-secondary)]">{label}</div>
      <div className="mt-1.5 font-display text-[24px] font-semibold leading-tight tracking-[-0.02em] tabular-nums text-[var(--color-text-primary)] sm:text-[28px]">
        {value}
      </div>
      <div className="mt-auto pt-3">
        <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-semibold ${meta.bg} ${meta.text}`}>
          {supportingText}
        </span>
      </div>
    </article>
  )
}
