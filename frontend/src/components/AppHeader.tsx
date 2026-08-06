import { useEffect, useId, useRef, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { BrandMark } from './BrandMark'

// Casca do app (Frente S) — substitui `DashboardHeader`. `plantName` é um slot
// reservado para o ADR-069 (multi-usina): quando ausente/undefined, este
// componente não renderiza absolutamente nada no lugar (nem placeholder, nem
// "Usina não identificada") — decisão já confirmada com o usuário.
export function AppHeader({ plantName }: { plantName?: string }) {
  const { username, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuId = useId()
  const containerRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!menuOpen) return

    function handleClickOutside(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setMenuOpen(false)
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenuOpen(false)
        buttonRef.current?.focus()
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [menuOpen])

  return (
    <header className="sticky top-0 z-30 bg-white border-b border-gray-200">
      <div className="mx-auto max-w-7xl 2xl:max-w-[96rem] px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <BrandMark className="h-7 w-auto text-[var(--color-brand-primary)] flex-shrink-0" />
          <span className="text-lg font-semibold text-gray-900 hidden sm:inline">Mplacas</span>
          {/* Reservado para o ADR-069 (multi-usina) — nunca renderiza nada
              quando `plantName` está ausente. */}
          {plantName && (
            <span className="truncate text-sm text-gray-500 border-l border-gray-200 pl-3 ml-1">
              {plantName}
            </span>
          )}
        </div>

        <div ref={containerRef} className="relative">
          <button
            ref={buttonRef}
            type="button"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            aria-label={username ? `Menu de ${username}` : 'Menu do usuário'}
            onClick={() => setMenuOpen((prev) => !prev)}
            className="flex items-center gap-2 rounded text-sm text-gray-700 hover:text-gray-900 transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
          >
            <span
              aria-hidden="true"
              className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-brand-primary-light)] text-[var(--color-brand-primary)] text-sm font-semibold"
            >
              {(username ?? '?').charAt(0).toUpperCase()}
            </span>
            <span aria-hidden="true" className={`text-xs transition-transform duration-150 ${menuOpen ? 'rotate-180' : ''}`}>
              ▾
            </span>
          </button>

          {menuOpen && (
            <div
              id={menuId}
              role="menu"
              className="absolute right-0 mt-2 w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
            >
              {username && (
                <div className="px-3 py-2 text-sm font-medium text-gray-900 border-b border-gray-100">
                  {username}
                </div>
              )}
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false)
                  logout()
                }}
                className="w-full rounded text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand-primary)]"
              >
                Sair
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
