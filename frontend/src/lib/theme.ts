// Mecanismo de resolução de tema (ADR-071, Decisão 1/2). Sem dependência
// externa — só lê/escreve `localStorage` e `matchMedia`, e aplica o atributo
// `data-theme` no `<html>`. Chamado uma única vez em `main.tsx`, antes do
// primeiro render (ver Decisão 2 do ADR: não há `<script>` inline no `<head>`
// por causa do CSP sem `unsafe-inline`/nonce, então um flash cosmético breve
// é aceito conscientemente em vez disso).

import { safeStorage } from './storage'

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
  const saved = safeStorage.get(STORAGE_KEY)
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
 * Lê a preferência atualmente persistida, nos três estados que o controle de
 * UI (Fase 3, `AppHeader`) precisa distinguir. Ausência da chave, ou valor
 * inválido (lixo, versão antiga etc.), é `'system'` — mesmo critério de
 * fallback de `resolveInitialTheme`, mas devolvendo a preferência (três
 * estados: qual opção marcar como atual), não o tema já resolvido (dois
 * estados: o que pintar na tela).
 */
export function getThemePreference(): ThemePreference {
  const saved = safeStorage.get(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') {
    return saved
  }
  return 'system'
}

/**
 * Persiste a escolha explícita do usuário (Decisão 1 do ADR). `'system'` não
 * grava um terceiro valor — remove a chave, já que ausência da chave já
 * significa "seguir o SO", mesmo espírito de só persistir preferência não
 * sensível (tema, não dado de negócio).
 */
export function setThemePreference(preference: ThemePreference): void {
  if (preference === 'system') {
    safeStorage.remove(STORAGE_KEY)
    return
  }
  safeStorage.set(STORAGE_KEY, preference)
}

/**
 * Resolve o tema efetivo (o que está realmente pintado na tela agora) a
 * partir de uma preferência de três estados. `'system'` consulta
 * `matchMedia` no momento da chamada; `'light'`/`'dark'` são o próprio tema,
 * sem indireção. Usado pelo botão-ícone único do controle de tema no header
 * (substitui a lista "Aparência" do menu do avatar): o ícone precisa
 * refletir o resultado visual atual (sol/lua), não a categoria abstrata da
 * preferência — quando a preferência é "Sistema", o ícone ainda mostra o
 * tema que o SO resolve neste instante.
 */
export function resolveEffectiveTheme(preference: ThemePreference): Theme {
  if (preference === 'system') {
    return prefersDark() ? 'dark' : 'light'
  }
  return preference
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
    if (safeStorage.get(STORAGE_KEY) !== null) {
      // Existe um override salvo — a preferência do SO não deve mais reaplicar.
      return
    }
    onChange(event.matches ? 'dark' : 'light')
  }

  media.addEventListener('change', listener)
  return () => media.removeEventListener('change', listener)
}
