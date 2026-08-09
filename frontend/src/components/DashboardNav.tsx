import { NavLink } from 'react-router'
import {
  DASHBOARD_FINANCIAL_PATH,
  DASHBOARD_OVERVIEW_PATH,
  DASHBOARD_PRODUCTION_PATH,
  DASHBOARD_TECHNICAL_PATH,
} from '../routes'

type NavIcon = 'overview' | 'production' | 'financial' | 'technical'

const NAV_ITEMS: ReadonlyArray<{ to: string; label: string; description: string; icon: NavIcon }> = [
  {
    to: DASHBOARD_OVERVIEW_PATH,
    label: 'Visão Geral',
    description: 'Cockpit executivo',
    icon: 'overview',
  },
  {
    to: DASHBOARD_PRODUCTION_PATH,
    label: 'Produção',
    description: 'Geração e desvios',
    icon: 'production',
  },
  {
    to: DASHBOARD_FINANCIAL_PATH,
    label: 'Financeiro',
    description: 'Economia e retorno',
    icon: 'financial',
  },
  {
    to: DASHBOARD_TECHNICAL_PATH,
    label: 'Técnico',
    description: 'Causas e performance',
    icon: 'technical',
  },
]

function NavItemIcon({ name }: { name: NavIcon }) {
  const paths: Record<NavIcon, string> = {
    overview: 'M4 13h6V4H4v9Zm0 7h6v-4H4v4Zm10 0h6v-9h-6v9Zm0-13h6V4h-6v3Z',
    production: 'M13 2 5.5 13h6L11 22l7.5-12h-6L13 2Z',
    financial: 'M4 7.5h14.5A1.5 1.5 0 0 1 20 9v8.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5v-11A1.5 1.5 0 0 1 5.5 5H17 M16 12h4v3h-4a1.5 1.5 0 0 1 0-3Z',
    technical: 'M12 3v3M12 18v3M3 12h3M18 12h3M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12M18.36 5.64l-2.12 2.12M7.76 16.24l-2.12 2.12 M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z',
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={paths[name]} />
    </svg>
  )
}

// Sub-navegação dos módulos do painel (ADR-072, Decisão 1/4). Renderizada
// pelo `DashboardLayout` via o slot `subnav` de `AppShell`, entre `AppHeader`
// e `<main>`. `NavLink` já aplica `aria-current="page"` no link ativo —
// nenhuma lógica extra necessária para isso.
export function DashboardNav() {
  return (
    <nav
      aria-label="Seções do painel"
      className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-2 shadow-sm"
    >
      <div className="hidden px-3 pb-3 pt-2 lg:block">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-brand-primary)]">
          Operação
        </p>
        <p className="mt-1 text-sm text-gray-500">
          Navegue pelos módulos do painel solar.
        </p>
      </div>
      <div className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            aria-label={item.label}
            className={({ isActive }) =>
              `group flex min-h-[52px] min-w-[9.25rem] items-center gap-2.5 whitespace-nowrap rounded-xl border px-2.5 text-sm font-semibold transition-all duration-200 active:translate-y-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none sm:min-h-[56px] sm:min-w-[10.5rem] sm:gap-3 sm:px-3 lg:min-w-0 ${
                isActive
                  ? 'border-[var(--color-brand-primary)] bg-[var(--color-brand-primary-light)] text-[var(--color-brand-primary)] shadow-sm'
                  : 'border-transparent text-gray-600 hover:-translate-y-0.5 hover:border-gray-200 hover:bg-gray-50 hover:text-gray-900 hover:shadow-sm'
              }`
            }
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/70 text-current ring-1 ring-inset ring-black/5 transition-transform duration-200 group-hover:scale-105 motion-reduce:transition-none sm:h-9 sm:w-9">
              <NavItemIcon name={item.icon} />
            </span>
            <span className="min-w-0 text-left">
              <span className="block truncate">{item.label}</span>
              <span className="block truncate text-xs font-medium text-gray-500 group-aria-[current=page]:text-[var(--color-brand-primary)]/80">
                {item.description}
              </span>
            </span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
