import { NavLink } from 'react-router'
import {
  DASHBOARD_FINANCIAL_PATH,
  DASHBOARD_OVERVIEW_PATH,
  DASHBOARD_PRODUCTION_PATH,
  DASHBOARD_TECHNICAL_PATH,
} from '../routes'

type NavIcon = 'overview' | 'production' | 'financial' | 'technical'

const NAV_ITEMS: ReadonlyArray<{ to: string; label: string; icon: NavIcon }> = [
  { to: DASHBOARD_OVERVIEW_PATH, label: 'Visão Geral', icon: 'overview' },
  { to: DASHBOARD_PRODUCTION_PATH, label: 'Produção', icon: 'production' },
  { to: DASHBOARD_FINANCIAL_PATH, label: 'Financeiro', icon: 'financial' },
  { to: DASHBOARD_TECHNICAL_PATH, label: 'Técnico', icon: 'technical' },
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
      className="border-b border-[var(--color-border)] bg-[var(--color-surface)]"
    >
      <div className="mx-auto max-w-7xl 2xl:max-w-[96rem] px-4 sm:px-6 lg:px-8 flex gap-1 overflow-x-auto">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex min-h-[44px] items-center gap-2 whitespace-nowrap border-b-2 px-3 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] ${
                isActive
                  ? 'border-[var(--color-brand-primary)] text-[var(--color-brand-primary)]'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`
            }
          >
            <NavItemIcon name={item.icon} />
            {item.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
