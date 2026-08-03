export function PriorityActionsCard({ actions }: { actions: string[] }) {
  if (actions.length === 0) return null

  return (
    <div className="mt-4 rounded-xl border border-gray-200 border-l-4 border-l-[var(--color-warning)] bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Ações prioritárias
      </p>
      <ul className="mt-3 space-y-2 text-sm text-gray-700">
        {actions.map((action) => (
          <li key={action} className="flex gap-2">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-warning)]" />
            <span>{action}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
