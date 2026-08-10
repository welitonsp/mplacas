import type { ReactNode } from 'react'
import type { Severity } from '../lib/dashboard/contracts'
import { SEVERITY_BG, SEVERITY_TEXT } from '../lib/dashboard/visuals'

export type OperationalStateTone = Severity | 'brand'
export type OperationalStateIcon = 'check' | 'empty' | 'warning' | 'sync'

const TONE_META: Record<OperationalStateTone, { bg: string; text: string; ring: string; border: string }> = {
  brand: {
    bg: 'bg-[var(--color-brand-primary-light)]',
    text: 'text-[var(--color-brand-primary)]',
    ring: 'ring-[var(--color-brand-primary)]/15',
    border: 'border-[var(--color-brand-primary)]/20',
  },
  success: {
    bg: SEVERITY_BG.success,
    text: SEVERITY_TEXT.success,
    ring: 'ring-[var(--color-success)]/15',
    border: 'border-[var(--color-success)]/25',
  },
  warning: {
    bg: SEVERITY_BG.warning,
    text: SEVERITY_TEXT.warning,
    ring: 'ring-[var(--color-warning)]/15',
    border: 'border-[var(--color-warning)]/25',
  },
  danger: {
    bg: SEVERITY_BG.danger,
    text: SEVERITY_TEXT.danger,
    ring: 'ring-[var(--color-danger)]/15',
    border: 'border-[var(--color-danger)]/25',
  },
  neutral: {
    bg: SEVERITY_BG.neutral,
    text: SEVERITY_TEXT.neutral,
    ring: 'ring-gray-200',
    border: 'border-[var(--color-border)]',
  },
}

function OperationalIcon({ icon, tone }: { icon: OperationalStateIcon; tone: OperationalStateTone }) {
  const meta = TONE_META[tone]

  return (
    <span
      className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${meta.bg} ${meta.text} ring-8 ${meta.ring}`}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 24 24"
        className="h-5 w-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {icon === 'check' ? (
          <>
            <path d="m5 12 4 4L19 6" />
            <path d="M12 21a9 9 0 1 0-8.48-6" />
          </>
        ) : icon === 'warning' ? (
          <>
            <path d="M12 8v4" />
            <path d="M12 16h.01" />
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
          </>
        ) : icon === 'sync' ? (
          <>
            <path d="M16.2 8.2A6.5 6.5 0 0 0 4.7 5.1L3.5 6.3" />
            <path d="M3.5 3v3.3h3.3" />
            <path d="M3.8 11.8a6.5 6.5 0 0 0 11.5 3.1l1.2-1.2" />
            <path d="M16.5 17v-3.3h-3.3" />
          </>
        ) : (
          <>
            <path d="M4 17.5V8.75A2.75 2.75 0 0 1 6.75 6h10.5A2.75 2.75 0 0 1 20 8.75v8.75" />
            <path d="M7 15.5h10" />
            <path d="M9 11h6" />
            <path d="M3 17.5h18" />
          </>
        )}
      </svg>
    </span>
  )
}

export function OperationalState({
  eyebrow,
  title,
  description,
  action,
  tone = 'neutral',
  icon = 'empty',
  role,
  ariaLabel,
  headingLevel = 2,
  align = 'center',
  actionClassName,
  className = '',
}: {
  eyebrow?: string
  title: string
  description: string
  action?: ReactNode
  tone?: OperationalStateTone
  icon?: OperationalStateIcon
  role?: 'status' | 'alert' | 'complementary'
  ariaLabel?: string
  headingLevel?: 2 | 3
  align?: 'center' | 'start'
  actionClassName?: string
  className?: string
}) {
  const meta = TONE_META[tone]
  const centered = align === 'center'
  const Heading = headingLevel === 3 ? 'h3' : 'h2'

  return (
    <section
      role={role}
      aria-label={ariaLabel}
      aria-live={role === 'alert' ? 'assertive' : role === 'status' ? 'polite' : undefined}
      className={`rounded-2xl border ${meta.border} bg-[var(--color-surface)] p-5 shadow-sm sm:p-6 ${className}`.trim()}
    >
      <div className={centered ? 'mx-auto max-w-2xl text-center' : 'flex min-w-0 gap-4'}>
        <div className={centered ? '' : 'pt-1'}>
          <OperationalIcon icon={icon} tone={tone} />
        </div>
        <div className={centered ? '' : 'min-w-0 flex-1'}>
          {eyebrow && (
            <p className={`${centered ? 'mt-6' : ''} text-xs font-semibold uppercase tracking-[0.18em] ${meta.text}`}>
              {eyebrow}
            </p>
          )}
          <Heading className={`${eyebrow ? 'mt-3' : centered ? 'mt-6' : ''} text-lg font-semibold tracking-tight text-gray-950`}>
            {title}
          </Heading>
          <p className={`${centered ? 'mx-auto' : ''} mt-2 max-w-xl text-sm leading-6 text-gray-600`}>
            {description}
          </p>
          {action && (
            <div className={actionClassName ?? (centered ? 'mt-6 flex justify-center' : 'mt-5 flex flex-wrap gap-3')}>
              {action}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
