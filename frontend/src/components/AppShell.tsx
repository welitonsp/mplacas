import type { ReactNode } from 'react'
import { AppHeader } from './AppHeader'

const MAIN_ID = 'conteudo'

// Casca do app (Frente S): header fixo + skip link + container/padding que
// antes vivia solto dentro de `DashboardPage`. `plantName` é repassado direto
// para `AppHeader` (reservado para o ADR-069, multi-usina).
export function AppShell({ children, plantName }: { children: ReactNode; plantName?: string }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <a
        href={`#${MAIN_ID}`}
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-gray-900 focus:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
      >
        Pular para o conteúdo
      </a>

      <AppHeader plantName={plantName} />

      <main id={MAIN_ID} className="mx-auto max-w-7xl 2xl:max-w-[96rem] px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  )
}
