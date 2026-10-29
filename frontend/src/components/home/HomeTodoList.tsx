import { Link } from 'react-router'
import { ChevronRight, ClipboardCheck, FileText, OctagonAlert, Settings2, type LucideIcon } from 'lucide-react'
import type { HomeTodo } from '../../lib/dashboard/home'
import { DASHBOARD_FINANCIAL_PATH, DASHBOARD_SETUP_PATH } from '../../routes'

const ROW_CLASS =
  'flex min-h-[44px] w-full items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3.5 text-left transition-colors duration-150 hover:border-[var(--color-gray-300)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none'

const LINK_TARGET: Record<'setup' | 'bills', { to: string; icon: LucideIcon }> = {
  setup: { to: DASHBOARD_SETUP_PATH, icon: Settings2 },
  bills: { to: `${DASHBOARD_FINANCIAL_PATH}#faturas`, icon: FileText },
}

function RowContent({ todo, icon: Icon }: { todo: HomeTodo; icon: LucideIcon }) {
  return (
    <>
      <Icon aria-hidden="true" className="h-5 w-5 shrink-0 text-[var(--color-brand-primary)]" />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-semibold text-[var(--color-text-primary)]">{todo.title}</span>
        <span className="text-[13px] leading-5 text-[var(--color-text-secondary)]">{todo.detail}</span>
      </span>
      <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-[var(--color-gray-400)]" />
    </>
  )
}

// "Precisa de você" (ADR-083): só tarefas com ação concreta.
// - "Nada pendente." só quando o cadastro foi de fato lido: falha ao ler não
//   vira "zero pendências" (indisponível nunca é zero).
// - Diagnóstico crítico abre a lista completa, que mora no próprio Início.
export function HomeTodoList({
  todos,
  setupStatus,
  calmNote,
  onOpenDiagnostics,
}: {
  todos: readonly HomeTodo[]
  setupStatus: 'ready' | 'loading' | 'error'
  calmNote: string | null
  onOpenDiagnostics: () => void
}) {
  return (
    <section aria-labelledby="home-todo-heading" className="flex flex-col gap-2.5">
      <h2 id="home-todo-heading" className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
        Precisa de você
      </h2>

      {todos.length > 0 && (
        <ul className="flex flex-col gap-2">
          {todos.map((todo) => (
            <li key={todo.key}>
              {todo.target === 'diagnostics' ? (
                <button type="button" onClick={onOpenDiagnostics} className={ROW_CLASS}>
                  <RowContent todo={todo} icon={OctagonAlert} />
                </button>
              ) : (
                <Link to={LINK_TARGET[todo.target].to} className={ROW_CLASS}>
                  <RowContent todo={todo} icon={LINK_TARGET[todo.target].icon} />
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}

      {todos.length === 0 && setupStatus === 'ready' && (
        <div className="flex items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3.5">
          <ClipboardCheck aria-hidden="true" className="h-5 w-5 shrink-0 text-[var(--color-success-text)]" />
          <p className="text-sm font-semibold text-[var(--color-text-primary)]">Nada pendente.</p>
        </div>
      )}

      {setupStatus === 'error' && (
        <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">
          Não foi possível conferir o cadastro e as faturas pendentes agora. Use Atualizar para tentar de novo.
        </p>
      )}

      {calmNote && <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">{calmNote}</p>}
    </section>
  )
}
