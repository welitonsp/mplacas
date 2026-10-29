import { Link } from 'react-router'
import { DASHBOARD_METHODOLOGY_PATH } from '../routes'

// Atalho para "Como calculamos" (ADR-086), no mesmo formato do cartão
// "Detalhes técnicos": uma linha, sem competir com os números da tela.
export function MethodologyLink({ subtitle }: { subtitle: string }) {
  return (
    <Link
      to={DASHBOARD_METHODOLOGY_PATH}
      className="mt-6 flex min-h-[56px] items-center justify-between gap-3 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4 shadow-[var(--shadow-card)] transition-colors duration-150 hover:border-[var(--color-gray-300)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none"
    >
      <span className="flex flex-col gap-0.5">
        <span className="text-sm font-semibold text-[var(--color-text-primary)]">Como calculamos</span>
        <span className="text-[13px] text-[var(--color-text-secondary)]">{subtitle}</span>
      </span>
      <span aria-hidden="true" className="text-lg text-[var(--color-gray-500)]">›</span>
    </Link>
  )
}
