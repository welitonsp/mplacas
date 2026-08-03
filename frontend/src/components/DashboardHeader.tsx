export function DashboardHeader({ onLogout }: { onLogout: () => void }) {
  return (
    <header className="bg-white border-b border-gray-200">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-900">Mplacas — Dashboard</h1>
        <button
          onClick={onLogout}
          className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
        >
          Sair
        </button>
      </div>
    </header>
  )
}
