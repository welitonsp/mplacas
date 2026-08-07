// Fonte única compartilhada dos tokens de cor do design system, para os dois
// temas (claro/escuro) — ver ADR-071 (docs/ADR-071-dark-mode.md), Decisão 7.
//
// Espelha literalmente os hex declarados em `src/index.css` (`:root` para
// LIGHT_TOKENS, `:root[data-theme="dark"]` para DARK_TOKENS). Isto existe
// porque o Vitest mocka todo import de `.css` (inclusive `?raw`) antes do
// Vite processar a query, então não há como ler o CSS real em runtime de
// teste — é a mesma limitação documentada no comentário original de
// `contrastRatio.test.ts` e no mesmo padrão de `GRID_HEX` em
// `lib/dashboard/visuals.ts`.
//
// Se um valor mudar em `index.css`, ele PRECISA mudar aqui também nos dois
// lugares (light/dark) — é exatamente o tipo de deriva que
// `contrastRatio.test.ts` deve pegar ao consumir este arquivo.

export const LIGHT_TOKENS = {
  '--color-brand-primary': '#2563eb',
  '--color-brand-primary-dark': '#1d4ed8',
  '--color-brand-primary-light': '#eff6ff',
  '--color-surface': '#ffffff',
  '--color-surface-subtle': '#f8fafc',
  '--color-border': '#e2e8f0',
  '--color-text-primary': '#0f172a',
  '--color-text-secondary': '#475569',
  '--color-danger': '#dc2626',
  '--color-danger-light': '#fef2f2',
  '--color-success': '#16a34a',
  '--color-success-light': '#f0fdf4',
  '--color-warning': '#d97706',
  '--color-warning-light': '#fffbeb',
  '--color-success-text': '#15803d',
  '--color-warning-text': '#b45309',
  '--color-danger-text': '#b91c1c',
  '--color-chart-reference': '#64748b',
  '--color-chart-track': '#e2e8f0',
  '--color-data-secondary': '#7c3aed',
  '--color-data-secondary-light': '#f5f3ff',

  // Paleta `gray-*` padrão do Tailwind v4 (`@tailwindcss/vite`), gerada como
  // `oklch(...)` em `@layer theme` (ver ADR-071, Contexto). Hex abaixo
  // convertidos por fórmula (OKLab → sRGB, Björn Ottosson) a partir dos
  // valores oklch exatos confirmados em `dist/assets/*.css` após
  // `npm run build` — não os hex "clássicos" do Tailwind v3, que divergem
  // ligeiramente (ex.: v3 gray-900 `#111827` vs. v4 real `#101828`).
  '--color-gray-50': '#f9fafb',
  '--color-gray-100': '#f3f4f6',
  '--color-gray-200': '#e5e7eb',
  '--color-gray-300': '#d1d5dc',
  '--color-gray-400': '#99a1af',
  '--color-gray-500': '#6a7282',
  '--color-gray-600': '#4a5565',
  '--color-gray-700': '#364153',
  '--color-gray-800': '#1e2939',
  '--color-gray-900': '#101828',
} as const

export const DARK_TOKENS = {
  '--color-brand-primary': '#5b8def',
  '--color-brand-primary-dark': '#8fb8ff',
  '--color-brand-primary-light': '#132038',
  '--color-surface': '#111a2b',
  '--color-surface-subtle': '#0a0f1c',
  '--color-border': '#2a3648',
  '--color-text-primary': '#eef1f7',
  '--color-text-secondary': '#9aa7bc',
  '--color-danger': '#ef4444',
  '--color-danger-light': '#2a1414',
  '--color-success': '#22c55e',
  '--color-success-light': '#0f2417',
  '--color-warning': '#f59e0b',
  '--color-warning-light': '#271b0a',
  '--color-success-text': '#4ade80',
  '--color-warning-text': '#fbbf24',
  '--color-danger-text': '#f87171',
  '--color-chart-reference': '#8291a8',
  '--color-chart-track': '#263144',
  '--color-data-secondary': '#c4b5fd',
  '--color-data-secondary-light': '#1e1b33',

  '--color-gray-50': '#0d1420',
  '--color-gray-100': '#161f30',
  '--color-gray-200': '#212c40',
  '--color-gray-300': '#3a4760',
  '--color-gray-400': '#78839a',
  '--color-gray-500': '#93a0b5',
  '--color-gray-600': '#b7c1d1',
  '--color-gray-700': '#d3dae5',
  '--color-gray-800': '#e6eaf1',
  '--color-gray-900': '#f3f5f9',
} as const

export type DesignTokenName = keyof typeof LIGHT_TOKENS
