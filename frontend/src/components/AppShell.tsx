import type { ReactNode } from 'react'
import { AppHeader } from './AppHeader'

const MAIN_ID = 'conteudo'

// Casca do app (Frente S): header fixo + skip link + container/padding que
// antes vivia solto dentro de `DashboardPage`. O `AppHeader` resolve o nome
// da usina sozinho, via `PlantSelector`/`PlantContext` (ADR-069, Etapa D).
//
// `subnav` (ADR-072, Etapa 1): slot opcional renderizado entre `AppHeader` e
// `<main>` — usado pelo `DashboardLayout` para o `DashboardNav` dos módulos.
// Fica FORA do `<main>` de propósito: o skip-link aponta para `#conteudo`, e
// não deve cair em cima de mais um nível de navegação.
export function AppShell({ children, subnav }: { children: ReactNode; subnav?: ReactNode }) {
  if (!subnav) {
    return (
      <div className="min-h-screen bg-[var(--color-surface-subtle)] text-[var(--color-text-primary)]">
        <a
          href={`#${MAIN_ID}`}
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-[var(--color-surface)] focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-gray-900 focus:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
        >
          Pular para o conteúdo
        </a>

        <AppHeader />

        <main id={MAIN_ID} className="mx-auto max-w-7xl 2xl:max-w-[96rem] px-3 py-5 sm:px-6 sm:py-8 lg:px-8 md:py-10">
          {children}
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--color-surface-subtle)] text-[var(--color-text-primary)]">
      <a
        href={`#${MAIN_ID}`}
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-[var(--color-surface)] focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-gray-900 focus:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
      >
        Pular para o conteúdo
      </a>

      <AppHeader />

      <div className="mx-auto grid max-w-7xl gap-4 px-3 py-4 sm:gap-6 sm:px-6 sm:py-6 md:py-8 lg:grid-cols-[16rem_minmax(0,1fr)] lg:px-8 xl:grid-cols-[17rem_minmax(0,1fr)] xl:gap-8 2xl:max-w-[96rem]">
        <aside className="lg:sticky lg:top-20 lg:self-start">
          {subnav}
        </aside>

        <main id={MAIN_ID} className="min-w-0">
          {children}
        </main>
      </div>
    </div>
  )
}
