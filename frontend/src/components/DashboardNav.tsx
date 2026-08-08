import { NavLink } from 'react-router'
import {
  DASHBOARD_FINANCIAL_PATH,
  DASHBOARD_OVERVIEW_PATH,
  DASHBOARD_PRODUCTION_PATH,
  DASHBOARD_TECHNICAL_PATH,
} from '../routes'

const NAV_ITEMS: ReadonlyArray<{ to: string; label: string }> = [
  { to: DASHBOARD_OVERVIEW_PATH, label: 'Visão Geral' },
  { to: DASHBOARD_PRODUCTION_PATH, label: 'Produção' },
  { to: DASHBOARD_FINANCIAL_PATH, label: 'Financeiro' },
  { to: DASHBOARD_TECHNICAL_PATH, label: 'Técnico' },
]

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
              `flex min-h-[44px] items-center whitespace-nowrap border-b-2 px-3 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] ${
                isActive
                  ? 'border-[var(--color-brand-primary)] text-[var(--color-brand-primary)]'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
