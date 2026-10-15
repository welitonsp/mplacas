import { useEffect, useId, useRef, useState } from 'react'
import { ChevronDown, LogOut, Moon, Sun } from 'lucide-react'
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

  // Cabeçalho (ADR-077, etapa 2): superfície lisa, marca uma vez só, usina ao
  // lado, controles "fantasma" à direita — sem pílulas com sombra e sem o
  // efeito de levantar no hover, que fazia cada botão parecer um cartão.
  const ghostButton =
    'flex min-h-[44px] items-center justify-center rounded-[var(--radius-control)] text-[var(--color-text-secondary)] transition-colors duration-150 hover:bg-[var(--color-gray-100)] hover:text-[var(--color-text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none'

  return (
    <header className="sticky top-0 z-30 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:gap-4 sm:px-6 lg:px-8 2xl:max-w-[96rem]">
        {/* A troca ícone ↔ marca completa fica num invólucro: o `BrandMark`
            tem `inline-flex` próprio, que vencia o `hidden` passado por
            `className` e mostrava as duas marcas no celular, empurrando o
            nome da usina para fora da tela. */}
        <span className="flex shrink-0 sm:hidden">
          <BrandMark showWordmark={false} />
        </span>
        <span className="hidden shrink-0 sm:flex">
          <BrandMark className="text-[var(--color-text-primary)]" />
        </span>
        <span aria-hidden="true" className="hidden h-6 w-px bg-[var(--color-border)] sm:block" />
        <PlantSelector />

        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={handleThemeToggle}
            aria-label={themeControlLabel}
            title={themeControlLabel}
            className={`${ghostButton} min-w-[44px]`}
          >
            {effectiveTheme === 'light' ? (
              <Sun aria-hidden="true" className="h-5 w-5" strokeWidth={1.9} />
            ) : (
              <Moon aria-hidden="true" className="h-5 w-5" strokeWidth={1.9} />
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
              className={`${ghostButton} gap-2 pl-1.5 pr-2`}
            >
              <span
                aria-hidden="true"
                className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-brand-primary-light)] text-sm font-bold text-[var(--color-brand-primary)]"
              >
                {operatorInitial}
              </span>
              <span className="hidden max-w-[12rem] truncate text-sm font-semibold text-[var(--color-text-primary)] md:block">
                {operatorDisplayName}
              </span>
              <ChevronDown
                aria-hidden="true"
                className={`h-4 w-4 transition-transform duration-150 motion-reduce:transition-none ${menuOpen ? 'rotate-180' : ''}`}
              />
            </button>

            {menuOpen && (
              <div
                id={menuId}
                role="menu"
                className="absolute right-0 mt-2 w-72 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[0_16px_40px_-12px_rgb(0_0_0_/_0.28)]"
              >
                <div className="flex items-center gap-3 border-b border-[var(--color-border)] px-4 py-3.5">
                  <span
                    aria-hidden="true"
                    className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-[var(--color-brand-primary-light)] text-sm font-bold text-[var(--color-brand-primary)]"
                  >
                    {operatorInitial}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs text-[var(--color-text-secondary)]">Sessão operacional</p>
                    <p className="truncate text-sm font-semibold text-[var(--color-text-primary)]">{operatorDisplayName}</p>
                    <p className="text-xs text-[var(--color-text-secondary)]">Acesso seguro ao painel</p>
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
                    className="flex min-h-[44px] w-full items-center gap-2.5 rounded-xl px-3 text-left text-sm font-semibold text-[var(--color-text-primary)] transition-colors duration-150 hover:bg-[var(--color-gray-100)] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand-primary)]"
                  >
                    <LogOut aria-hidden="true" className="h-4 w-4 flex-shrink-0" />
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
