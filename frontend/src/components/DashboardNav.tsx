import { NavLink } from 'react-router'
import { useMe } from '../contexts/MeContext'
import {
  DASHBOARD_CLIENTS_PATH,
  DASHBOARD_FINANCIAL_PATH,
  DASHBOARD_OVERVIEW_PATH,
  DASHBOARD_PRODUCTION_PATH,
  DASHBOARD_SETUP_PATH,
} from '../routes'

import { House, Settings2, Users, Wallet, Zap, type LucideIcon } from 'lucide-react'

type NavKey = 'overview' | 'production' | 'financial' | 'setup' | 'clients'

// Quatro abas, uma pergunta cada (ADR-083). "Energia" fica ativa também em
// `/dashboard/energia/tecnico` (os detalhes técnicos moram dentro dela): o
// `NavLink` sem `end` casa as rotas descendentes.
//
// `shortLabel`: rótulo da barra do celular quando o completo quebraria em duas
// linhas. O nome acessível continua sendo o `label`.
const NAV_ITEMS: ReadonlyArray<{
  key: NavKey
  to: string
  label: string
  shortLabel?: string
  icon: LucideIcon
}> = [
  { key: 'overview', to: DASHBOARD_OVERVIEW_PATH, label: 'Início', icon: House },
  { key: 'production', to: DASHBOARD_PRODUCTION_PATH, label: 'Energia', icon: Zap },
  { key: 'financial', to: DASHBOARD_FINANCIAL_PATH, label: 'Dinheiro', icon: Wallet },
  // Cadastro feito pelo próprio cliente (o sistema será vendido a outros
  // donos de usina) — por último, porque é consultado menos que os módulos.
  // Sem `shortLabel`: "Minha usina" cabe na barra do celular (360 px, 4 itens
  // de ~90 px, 12 px de letra). Com a 5ª aba do dono, ver `DashboardNav`. O mesmo item tinha dois nomes ("Usina" no
  // celular, "Minha usina" no desktop) — auditoria visual, item 16.
  { key: 'setup', to: DASHBOARD_SETUP_PATH, label: 'Minha usina', icon: Settings2 },
]

// Só o dono da plataforma (ADR-093): convidar e acompanhar clientes. Quinta
// aba, escondida de todo cliente.
const CLIENTS_ITEM: (typeof NAV_ITEMS)[number] = {
  key: 'clients',
  to: DASHBOARD_CLIENTS_PATH,
  label: 'Clientes',
  icon: Users,
}

// Navegação dos módulos (ADR-072; visual ADR-077, etapa 2).
//
// UM único <nav>, dois arranjos por CSS: no celular/tablet é uma barra fixa no
// rodapé com ícone sobre o rótulo (padrão Material/iOS — o polegar alcança, e
// as 4 abas ficam sempre visíveis); a partir de `lg` vira a lista lateral.
// Um só conjunto de links evita leitor de tela ouvir a navegação duas vezes.
//
// Saiu o "roteiro executivo" (pergunta-chave, foco, entregável, rotina de
// leitura): texto fixo repetido em toda tela, que empurrava o conteúdo e
// competia com o título do módulo.
export function DashboardNav() {
  const { me } = useMe()
  // Com 5 abas (dono da plataforma), cada uma tem ~66 px no celular de 360 px:
  // "Minha usina" quebraria em duas linhas, então ganha o rótulo curto "Usina".
  const items = me?.isPlatformOperator
    ? [
        ...NAV_ITEMS.map((item) => (item.key === 'setup' ? { ...item, shortLabel: 'Usina' } : item)),
        CLIENTS_ITEM,
      ]
    : NAV_ITEMS
  return (
    <nav
      aria-label="Seções do painel"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-[var(--color-border)] bg-[var(--color-surface)] pb-[env(safe-area-inset-bottom)] lg:static lg:border-0 lg:bg-transparent lg:pb-0"
    >
      <ul
        className={`mx-auto grid max-w-xl gap-1 px-2 py-1.5 lg:max-w-none lg:grid-cols-1 lg:gap-1 lg:p-0 ${
          items.length > 4 ? 'grid-cols-5' : 'grid-cols-4'
        }`}
      >
        {items.map(({ key, to, label, shortLabel, icon: Icon }) => (
          <li key={key}>
            <NavLink
              to={to}
              aria-label={label}
              className={({ isActive }) =>
                `group flex min-h-[56px] flex-col items-center justify-center gap-1 rounded-xl text-xs font-semibold transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none lg:min-h-[44px] lg:flex-row lg:justify-start lg:gap-3 lg:px-3 lg:text-sm ${
                  isActive
                    ? 'text-[var(--color-brand-primary)] lg:bg-[var(--color-brand-primary-light)]'
                    : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] lg:font-medium lg:hover:bg-[var(--color-gray-100)]'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    aria-hidden="true"
                    className={`flex h-8 w-14 items-center justify-center rounded-full transition-colors duration-150 motion-reduce:transition-none lg:h-auto lg:w-auto lg:bg-transparent ${
                      isActive ? 'bg-[var(--color-brand-primary-light)]' : ''
                    }`}
                  >
                    <Icon className="h-5 w-5" strokeWidth={isActive ? 2.2 : 1.9} />
                  </span>
                  {shortLabel ? (
                    <>
                      <span className="lg:hidden">{shortLabel}</span>
                      <span className="hidden lg:inline">{label}</span>
                    </>
                  ) : (
                    <span>{label}</span>
                  )}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
