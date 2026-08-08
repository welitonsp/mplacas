// Mecanismo de resolução de tema (ADR-071, Decisão 1/2). Sem dependência
// externa — só lê/escreve `localStorage` e `matchMedia`, e aplica o atributo
// `data-theme` no `<html>`. Chamado uma única vez em `main.tsx`, antes do
// primeiro render (ver Decisão 2 do ADR: não há `<script>` inline no `<head>`
// por causa do CSP sem `unsafe-inline`/nonce, então um flash cosmético breve
// é aceito conscientemente em vez disso).

export type Theme = 'light' | 'dark'
export type ThemePreference = Theme | 'system'

const STORAGE_KEY = 'mplacas:theme'

function prefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

/**
 * Resolve o tema inicial: override salvo (`'light'`/`'dark'`) vence se
 * presente e válido; ausência de chave ou valor salvo inválido (lixo,
 * versão antiga etc.) cai para a preferência do SO via `matchMedia`.
 */
export function resolveInitialTheme(): Theme {
  const saved = window.localStorage.getItem(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') {
    return saved
  }
  return prefersDark() ? 'dark' : 'light'
}

/** Aplica o tema resolvido ao DOM — único ponto que a cascata CSS observa. */
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
}

/**
 * Persiste a escolha explícita do usuário (Decisão 1 do ADR). `'system'` não
 * grava um terceiro valor — remove a chave, já que ausência da chave já
 * significa "seguir o SO", mesmo espírito de só persistir preferência não
 * sensível que `mplacas:technical-performance-expanded` já usa.
 */
export function setThemePreference(preference: ThemePreference): void {
  if (preference === 'system') {
    window.localStorage.removeItem(STORAGE_KEY)
    return
  }
  window.localStorage.setItem(STORAGE_KEY, preference)
}

/**
 * Observa mudança de preferência do SO em tempo real e chama `onChange` com
 * o novo tema resolvido — mas só enquanto não houver override salvo (Decisão
 * 1: uma vez que o usuário escolhe manualmente, o SO deixa de ditar o tema).
 * Retorna a função de cleanup, para uso dentro de um `useEffect` (Fase 3).
 */
export function watchSystemTheme(onChange: (theme: Theme) => void): () => void {
  const media = window.matchMedia('(prefers-color-scheme: dark)')

  const listener = (event: MediaQueryListEvent) => {
    if (window.localStorage.getItem(STORAGE_KEY) !== null) {
      // Existe um override salvo — a preferência do SO não deve mais reaplicar.
      return
    }
    onChange(event.matches ? 'dark' : 'light')
  }

  media.addEventListener('change', listener)
  return () => media.removeEventListener('change', listener)
}
