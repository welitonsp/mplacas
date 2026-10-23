import { TriangleAlert, Check, Clock, OctagonAlert, type LucideIcon } from 'lucide-react'
import type { HomeStatus, HomeTone } from '../../lib/dashboard/home'

const TONE: Record<HomeTone, { box: string; badge: string; text: string; icon: LucideIcon }> = {
  success: {
    box: 'bg-[var(--color-success-light)]',
    badge: 'bg-[var(--color-success)] text-[var(--color-on-brand)]',
    text: 'text-[var(--color-success-text)]',
    icon: Check,
  },
  warning: {
    box: 'bg-[var(--color-warning-light)]',
    badge: 'bg-[var(--color-warning)] text-[var(--color-on-brand)]',
    text: 'text-[var(--color-warning-text)]',
    icon: TriangleAlert,
  },
  danger: {
    box: 'bg-[var(--color-danger-light)]',
    badge: 'bg-[var(--color-danger)] text-[var(--color-on-brand)]',
    text: 'text-[var(--color-danger-text)]',
    icon: OctagonAlert,
  },
  neutral: {
    box: 'bg-[var(--color-brand-primary-light)]',
    badge: 'bg-[var(--color-brand-primary)] text-[var(--color-on-brand)]',
    text: 'text-[var(--color-text-primary)]',
    icon: Clock,
  },
}

// Frase única de situação no topo do Início (ADR-083). A cor acompanha o
// ícone e o texto — nunca é a única portadora do estado.
export function HomeStatusCard({ status }: { status: HomeStatus }) {
  const tone = TONE[status.tone]
  const Icon = tone.icon
  return (
    <section
      aria-label="Situação da usina"
      data-testid="home-status"
      data-tone={status.tone}
      className={`flex items-center gap-3.5 rounded-[var(--radius-card)] p-4 sm:p-5 ${tone.box}`}
    >
      <span
        aria-hidden="true"
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${tone.badge}`}
      >
        <Icon className="h-5 w-5" strokeWidth={2.4} />
      </span>
      <div className="min-w-0">
        <h2 className={`font-display text-[18px] font-semibold leading-snug sm:text-[20px] ${tone.text}`}>
          {status.title}
        </h2>
        <p className={`mt-0.5 text-[14px] leading-5 ${tone.text}`}>{status.detail}</p>
      </div>
    </section>
  )
}
