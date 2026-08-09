import type { ReactNode } from 'react'
import type { Severity } from '../lib/dashboard/contracts'
import { SEVERITY_BG, SEVERITY_TEXT } from '../lib/dashboard/visuals'

type EmptyStateTone = Severity | 'brand'

const TONE_META: Record<EmptyStateTone, { bg: string; text: string; ring: string }> = {
  brand: {
    bg: 'bg-[var(--color-brand-primary-light)]',
    text: 'text-[var(--color-brand-primary)]',
    ring: 'ring-[var(--color-brand-primary)]/15',
  },
  success: {
    bg: SEVERITY_BG.success,
    text: SEVERITY_TEXT.success,
    ring: 'ring-[var(--color-success)]/15',
  },
  warning: {
    bg: SEVERITY_BG.warning,
    text: SEVERITY_TEXT.warning,
    ring: 'ring-[var(--color-warning)]/15',
  },
  danger: {
    bg: SEVERITY_BG.danger,
    text: SEVERITY_TEXT.danger,
    ring: 'ring-[var(--color-danger)]/15',
  },
  neutral: {
    bg: SEVERITY_BG.neutral,
    text: SEVERITY_TEXT.neutral,
    ring: 'ring-gray-200',
  },
}

function EmptyStateIcon({ tone }: { tone: EmptyStateTone }) {
  const meta = TONE_META[tone]

  return (
    <span className={`inline-flex h-11 w-11 items-center justify-center rounded-2xl ${meta.bg} ${meta.text} ring-8 ${meta.ring}`}>
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 17.5V8.75A2.75 2.75 0 0 1 6.75 6h10.5A2.75 2.75 0 0 1 20 8.75v8.75" />
        <path d="M7 15.5h10" />
        <path d="M9 11h6" />
        <path d="M3 17.5h18" />
      </svg>
    </span>
  )
}

export function EmptyState({
  eyebrow,
  title,
  description,
  action,
  tone = 'neutral',
  className = '',
}: {
  eyebrow?: string
  title: string
  description: string
  action?: ReactNode
  tone?: EmptyStateTone
  className?: string
}) {
  return (
    <div className={`rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-10 text-center shadow-sm ${className}`.trim()}>
      <EmptyStateIcon tone={tone} />
      {eyebrow && (
        <p className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-brand-primary)]">
          {eyebrow}
        </p>
      )}
      <h2 className="mt-3 text-lg font-semibold tracking-tight text-gray-950">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-gray-600">{description}</p>
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  )
}
