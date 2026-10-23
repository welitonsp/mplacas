import { Link } from 'react-router'
import { ChevronRight, ClipboardCheck, FileText, Settings2, Zap, type LucideIcon } from 'lucide-react'
import type { HomeTodo, HomeTodoTarget } from '../../lib/dashboard/home'
import { DASHBOARD_FINANCIAL_PATH, DASHBOARD_PRODUCTION_PATH, DASHBOARD_SETUP_PATH } from '../../routes'

const TARGET: Record<HomeTodoTarget, { to: string; icon: LucideIcon }> = {
  setup: { to: DASHBOARD_SETUP_PATH, icon: Settings2 },
  bills: { to: DASHBOARD_FINANCIAL_PATH, icon: FileText },
  energy: { to: DASHBOARD_PRODUCTION_PATH, icon: Zap },
}

// "Precisa de você" (ADR-083): só tarefas com ação concreta. Sem tarefa, diz
// isso com todas as letras e explica, uma vez, o que não exige ação (ex.:
// dias sem leitura num ciclo fechado).
export function HomeTodoList({ todos, calmNote }: { todos: readonly HomeTodo[]; calmNote: string | null }) {
  return (
    <section aria-labelledby="home-todo-heading" className="flex flex-col gap-2.5">
      <h2 id="home-todo-heading" className="font-display text-[18px] font-semibold text-[var(--color-text-primary)]">
        Precisa de você
      </h2>

      {todos.length === 0 ? (
        <div className="flex items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3.5">
          <ClipboardCheck aria-hidden="true" className="h-5 w-5 shrink-0 text-[var(--color-success-text)]" />
          <p className="text-[15px] font-semibold text-[var(--color-text-primary)]">Nada pendente.</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {todos.map((todo) => {
            const { to, icon: Icon } = TARGET[todo.target]
            return (
              <li key={todo.key}>
                <Link
                  to={to}
                  className="flex min-h-[44px] items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3.5 transition-colors duration-150 hover:border-[var(--color-gray-300)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none"
                >
                  <Icon aria-hidden="true" className="h-5 w-5 shrink-0 text-[var(--color-brand-primary)]" />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-[15px] font-semibold text-[var(--color-text-primary)]">{todo.title}</span>
                    <span className="text-[13px] leading-5 text-[var(--color-text-secondary)]">{todo.detail}</span>
                  </span>
                  <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-[var(--color-gray-400)]" />
                </Link>
              </li>
            )
          })}
        </ul>
      )}

      {calmNote && <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">{calmNote}</p>}
    </section>
  )
}
