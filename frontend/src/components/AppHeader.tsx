import { useEffect, useId, useRef, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { BrandMark } from './BrandMark'
import { PlantSelector } from './PlantSelector'
import {
  applyTheme,
  getThemePreference,
  resolveEffectiveTheme,
  setThemePreference,
  watchSystemTheme,
} from '../lib/theme'
import type { Theme, ThemePreference } from '../lib/theme'

// Três estados do controle de tema (ADR-071, Decisão 6), na mesma ordem em
// que o ícone único do header cicla a cada clique: Sistema é o default
// (nenhuma chave em `localStorage`, ver `getThemePreference`).
const THEME_OPTIONS: ReadonlyArray<{ value: ThemePreference; label: string }> = [
  { value: 'system', label: 'Sistema' },
  { value: 'light', label: 'Claro' },
  { value: 'dark', label: 'Escuro' },
]

const EFFECTIVE_THEME_LABELS: Record<Theme, string> = {
  light: 'claro',
  dark: 'escuro',
}

function themePreferenceLabel(preference: ThemePreference): string {
  return THEME_OPTIONS.find((option) => option.value === preference)?.label ?? preference
}

function nextThemePreference(current: ThemePreference): ThemePreference {
  const currentIndex = THEME_OPTIONS.findIndex((option) => option.value === current)
  return THEME_OPTIONS[(currentIndex + 1) % THEME_OPTIONS.length].value
}

// Texto que serve tanto de `aria-label` quanto de `title` (tooltip nativo)
// do botão-ícone de tema: estado atual + o que o próximo clique vai fazer.
// É o que substitui, em termos de acessibilidade, a lista de texto que
// existia antes dentro do menu do avatar — o leitor de tela nunca vê só o
// ícone sol/lua sem essa descrição.
function describeThemeControl(preference: ThemePreference, effectiveTheme: Theme): string {
  const next = nextThemePreference(preference)
  const current =
    preference === 'system'
      ? `Sistema (aplicando ${EFFECTIVE_THEME_LABELS[effectiveTheme]})`
      : themePreferenceLabel(preference)
  return `Tema: ${current}. Clique para mudar para ${themePreferenceLabel(next).toLowerCase()}.`
}

// Sol/lua em ~20x20, `currentColor`, sem biblioteca de ícones — mesmo padrão
// de SVG inline de `BrandMark`. `aria-hidden`: o texto acessível do controle
// vive inteiro no `aria-label`/`title` do botão, o ícone é só reforço visual.
function SunIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className={className} fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="10" cy="10" r="4" fill="currentColor" />
      <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
        <line x1="10" y1="1.5" x2="10" y2="4" />
        <line x1="10" y1="16" x2="10" y2="18.5" />
        <line x1="1.5" y1="10" x2="4" y2="10" />
        <line x1="16" y1="10" x2="18.5" y2="10" />
        <line x1="5.76" y1="5.76" x2="3.99" y2="3.99" />
        <line x1="14.24" y1="5.76" x2="16.01" y2="3.99" />
        <line x1="5.76" y1="14.24" x2="3.99" y2="16.01" />
        <line x1="14.24" y1="14.24" x2="16.01" y2="16.01" />
      </g>
    </svg>
  )
}

function MoonIcon({ className }: { className?: string }) {
  const maskId = useId()
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className={className} fill="none" xmlns="http://www.w3.org/2000/svg">
      <mask id={maskId}>
        <rect width="20" height="20" fill="white" />
        <circle cx="13.5" cy="7" r="5" fill="black" />
      </mask>
      <circle cx="10" cy="10" r="7.5" fill="currentColor" mask={`url(#${maskId})`} />
    </svg>
  )
}

// Casca do app (Frente S) — substitui `DashboardHeader`. O nome/seletor de
// usina (ADR-069, Etapa D) é resolvido pelo próprio `PlantSelector`, que lê o
// `PlantContext` diretamente: dropdown com múltiplas usinas, texto simples
// com uma só, nada com zero. `AppHeader` só precisa estar dentro do
// `PlantProvider`, o que já é garantido pela composição em `App.tsx`.
export function AppHeader() {
  const { username, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const [themePreference, setThemePreferenceState] = useState<ThemePreference>(() => getThemePreference())
  const [effectiveTheme, setEffectiveThemeState] = useState<Theme>(() => resolveEffectiveTheme(getThemePreference()))
  const menuId = useId()
  const containerRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const operatorDisplayName = username ?? 'Usuário autenticado'
  const operatorInitial = operatorDisplayName.charAt(0).toUpperCase()

  // Enquanto a opção ativa for "Sistema", reage a mudança de preferência do
  // SO em tempo real (ADR-071, Decisão 1/6). Ao trocar para uma opção manual
  // (`themePreference` muda), o efeito reexecuta: o cleanup remove o
  // listener antigo e o corpo novo retorna sem reassinar, porque a condição
  // abaixo já não é mais "system". Também atualiza `effectiveTheme`, para o
  // ícone sol/lua do header acompanhar a mudança do SO em tempo real.
  useEffect(() => {
    if (themePreference !== 'system') return

    return watchSystemTheme((theme) => {
      applyTheme(theme)
      setEffectiveThemeState(theme)
    })
  }, [themePreference])

  // Reaproveitada pelo botão-ícone único do header (antes era chamada pelos
  // 3 `<button role="menuitemradio">` da lista "Aparência" dentro do menu do
  // avatar). Lógica de resolução inalterada, só centralizada em
  // `resolveEffectiveTheme` (`lib/theme.ts`) em vez de repetir a checagem de
  // `matchMedia` aqui.
  function handleThemeSelect(preference: ThemePreference) {
    setThemePreference(preference)
    setThemePreferenceState(preference)
    const resolved = resolveEffectiveTheme(preference)
    applyTheme(resolved)
    setEffectiveThemeState(resolved)
  }

  // Um clique cicla system → light → dark → system (ordem de `THEME_OPTIONS`).
  function handleThemeToggle() {
    handleThemeSelect(nextThemePreference(themePreference))
  }

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

  const themeControlLabel = describeThemeControl(themePreference, effectiveTheme)

  return (
    <header className="sticky top-0 z-30 border-b border-[var(--color-border)] bg-[var(--color-surface)]/90 shadow-sm backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-3 sm:h-16 sm:px-6 lg:px-8 2xl:max-w-[96rem]">
        <div className="flex items-center gap-3 min-w-0">
          <BrandMark className="h-7 w-auto text-[var(--color-brand-primary)] flex-shrink-0" />
          <span className="hidden text-lg font-semibold tracking-tight text-gray-950 sm:inline">Mplacas</span>
          <PlantSelector />
        </div>

        <div className="flex items-center gap-2">
          {/* Ícone único, sempre visível: sol/lua conforme o tema efetivo
              atual. Substitui a lista "Aparência" que ficava escondida
              dentro do menu do avatar — o usuário não precisa mais abrir
              nenhum menu para ver ou mudar o tema. */}
          <button
            type="button"
            onClick={handleThemeToggle}
            aria-label={themeControlLabel}
            title={themeControlLabel}
            className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-full border border-gray-200 bg-gray-50 text-gray-700 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:text-gray-900 hover:shadow-md active:translate-y-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none"
          >
            {effectiveTheme === 'light' ? (
              <SunIcon className="h-5 w-5" />
            ) : (
              <MoonIcon className="h-5 w-5" />
            )}
          </button>

          <div ref={containerRef} className="relative">
            <button
              ref={buttonRef}
              type="button"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-controls={menuId}
              aria-label={username ? `Menu de ${username}` : 'Menu do usuário'}
              onClick={() => setMenuOpen((prev) => !prev)}
              className="flex min-h-[44px] items-center gap-2 rounded-full border border-gray-200 bg-gray-50 pl-1.5 pr-2 text-sm text-gray-700 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-white hover:text-gray-900 hover:shadow-md active:translate-y-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none"
            >
              <span
                aria-hidden="true"
                className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-brand-primary-light)] text-[var(--color-brand-primary)] text-sm font-semibold"
              >
                {operatorInitial}
              </span>
              <span className="hidden min-w-0 text-left md:block">
                <span className="block text-[12px] font-semibold uppercase leading-4 tracking-[0.12em] text-[var(--color-text-muted)]">
                  Operador
                </span>
                <span className="block max-w-[10rem] truncate text-sm font-semibold leading-5 text-gray-900">
                  {operatorDisplayName}
                </span>
              </span>
              <span aria-hidden="true" className={`text-xs transition-transform duration-150 ${menuOpen ? 'rotate-180' : ''}`}>
                ▾
              </span>
            </button>

            {menuOpen && (
              <div
                id={menuId}
                role="menu"
                className="absolute right-0 mt-2 w-72 overflow-hidden rounded-2xl border border-gray-200 bg-[var(--color-surface)] shadow-xl"
              >
                <div className="border-b border-gray-100 bg-[var(--color-surface-subtle)] px-4 py-3">
                  <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                    Sessão operacional
                  </p>
                  <div className="mt-2 flex items-center gap-3">
                    <span
                      aria-hidden="true"
                      className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-[var(--color-brand-primary-light)] text-sm font-bold text-[var(--color-brand-primary)]"
                    >
                      {operatorInitial}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-gray-950">{operatorDisplayName}</p>
                      <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">Acesso seguro ao painel</p>
                    </div>
                  </div>
                </div>

                <div className="p-1.5">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false)
                      logout()
                    }}
                    className="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-gray-700 transition-colors duration-150 hover:bg-gray-50 hover:text-gray-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand-primary)]"
                  >
                    <svg
                      viewBox="0 0 20 20"
                      aria-hidden="true"
                      className="h-4 w-4 flex-shrink-0"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M8 5.5V4a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-5a2 2 0 0 1-2-2v-1.5"
                        stroke="currentColor"
                        strokeWidth="1.7"
                        strokeLinecap="round"
                      />
                      <path
                        d="M3 10h8m0 0L8.25 7.25M11 10l-2.75 2.75"
                        stroke="currentColor"
                        strokeWidth="1.7"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    Sair do painel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}
