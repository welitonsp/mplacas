import { describe, expect, it } from 'vitest'
import { DARK_TOKENS, LIGHT_TOKENS, type DesignTokenName } from './designTokens'

// Cálculo real de contraste WCAG 2.2 (fórmula de luminância relativa, não um
// número hardcoded) — ver Etapa 1.1 do roteiro de UI/UX
// (docs/UI_UX_IMPLEMENTATION_ROADMAP_2026-08-04.md), a medição original em
// docs/UI_UX_AUDIT_2026-08-04.md (P1-03), e a extensão para dois temas em
// docs/ADR-071-dark-mode.md (Decisão 4/5/7 — dark mode, tokens de tema).
//
// Os hex vêm de `./designTokens.ts` (LIGHT_TOKENS/DARK_TOKENS), que espelham
// literalmente `src/index.css` (`:root` e `:root[data-theme="dark"]`) — mesmo
// padrão de `GRID_HEX` em `lib/dashboard/visuals.ts`: uma cópia documentada,
// não uma leitura em runtime do CSS (`import.meta.glob(..., { query: '?raw'
// })` não funciona para `.css` neste projeto porque o Vitest intercepta e
// mocka todo import de `.css`, inclusive com `?raw`, antes mesmo de o Vite
// processar a query — verificado experimentalmente). Se um destes hex mudar
// em `index.css`, ele PRECISA mudar em `designTokens.ts` também — é
// exatamente o tipo de deriva que este teste deve pegar (fechou, por
// construção, a deriva já encontrada entre `--color-chart-reference`
// `#6b7280` neste teste e `#64748b` em `index.css`, ver ADR-071 Contexto).

function hexToRgb(hex: string): [number, number, number] {
  const value = hex.replace('#', '')
  const r = parseInt(value.slice(0, 2), 16)
  const g = parseInt(value.slice(2, 4), 16)
  const b = parseInt(value.slice(4, 6), 16)
  return [r, g, b]
}

function channelLuminance(channel: number): number {
  const c = channel / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex)
  return 0.2126 * channelLuminance(r) + 0.7152 * channelLuminance(g) + 0.0722 * channelLuminance(b)
}

// Fórmula WCAG 2.x: (L1 + 0.05) / (L2 + 0.05), L1 = luminância da cor mais clara.
function contrastRatio(hexA: string, hexB: string): number {
  const lumA = relativeLuminance(hexA)
  const lumB = relativeLuminance(hexB)
  const lighter = Math.max(lumA, lumB)
  const darker = Math.min(lumA, lumB)
  return (lighter + 0.05) / (darker + 0.05)
}

const LIGHT_BG = {
  surface: LIGHT_TOKENS['--color-surface'],
  surfaceSubtle: LIGHT_TOKENS['--color-surface-subtle'],
}
const DARK_BG = {
  surface: DARK_TOKENS['--color-surface'],
  surfaceSubtle: DARK_TOKENS['--color-surface-subtle'],
}

// Pares "texto normal" obrigatórios pelo ADR-071 (Decisão 4/5/Validação):
// text-primary, text-secondary, os três `-text` de severidade,
// chart-reference, data-secondary, brand-primary, e a escala gray-500 a
// gray-900 (gray-400 é tratado à parte, ver bloco dedicado abaixo — é uma
// exceção conhecida, não uma regressão).
const TEXT_PAIRS: Array<[string, DesignTokenName]> = [
  ['text-primary', '--color-text-primary'],
  ['text-secondary', '--color-text-secondary'],
  ['success-text', '--color-success-text'],
  ['warning-text', '--color-warning-text'],
  ['danger-text', '--color-danger-text'],
  ['chart-reference', '--color-chart-reference'],
  ['data-secondary', '--color-data-secondary'],
  ['brand-primary', '--color-brand-primary'],
  ['gray-500', '--color-gray-500'],
  ['gray-600', '--color-gray-600'],
  ['gray-700', '--color-gray-700'],
  ['gray-800', '--color-gray-800'],
  ['gray-900', '--color-gray-900'],
]

// Tokens de PREENCHIMENTO (badge/barra/ponto — nunca `color` de texto, ver
// comentário em `index.css`), exigem só 3:1 (WCAG 1.4.11, elemento gráfico).
// `--color-chart-track` fica de fora deliberadamente: é o trilho/fundo do
// gráfico, não o elemento que carrega significado (ADR-071 Decisão 4 marca
// esse par com "—", sem exigência de contraste).
const FILL_PAIRS: Array<[string, DesignTokenName]> = [
  ['success', '--color-success'],
  ['warning', '--color-warning'],
  ['danger', '--color-danger'],
]

// Padrão de "badge": texto `-text` sobre o próprio fundo `-light` da mesma
// cor (SEVERITY_BG + SEVERITY_TEXT em `lib/dashboard/visuals.ts`) — exige
// 4.5:1 como qualquer texto normal. Números batem exatamente com
// ADR-071 Decisão 5 para o tema escuro.
const TEXT_ON_OWN_LIGHT_BG_PAIRS: Array<[string, DesignTokenName, DesignTokenName]> = [
  ['success-text sobre success-light', '--color-success-text', '--color-success-light'],
  ['warning-text sobre warning-light', '--color-warning-text', '--color-warning-light'],
  ['danger-text sobre danger-light', '--color-danger-text', '--color-danger-light'],
  ['data-secondary sobre data-secondary-light', '--color-data-secondary', '--color-data-secondary-light'],
]

describe.each([
  ['claro', LIGHT_TOKENS, LIGHT_BG] as const,
  ['escuro', DARK_TOKENS, DARK_BG] as const,
])('contraste WCAG 2.2 — tema %s (calculado por fórmula, não hardcoded)', (_themeName, tokens, bg) => {
  it.each(TEXT_PAIRS)(
    '%s sobre --color-surface atende 4.5:1 (texto normal, WCAG 1.4.3 AA)',
    (_label, tokenName) => {
      const ratio = contrastRatio(tokens[tokenName], bg.surface)
      expect(ratio).toBeGreaterThanOrEqual(4.5)
    },
  )

  it.each(TEXT_PAIRS)(
    '%s sobre --color-surface-subtle atende 4.5:1 (texto normal, WCAG 1.4.3 AA)',
    (_label, tokenName) => {
      const ratio = contrastRatio(tokens[tokenName], bg.surfaceSubtle)
      expect(ratio).toBeGreaterThanOrEqual(4.5)
    },
  )

  it.each(FILL_PAIRS)(
    '%s (preenchimento) sobre --color-surface atende 3:1 (elemento gráfico, WCAG 1.4.11)',
    (_label, tokenName) => {
      const ratio = contrastRatio(tokens[tokenName], bg.surface)
      expect(ratio).toBeGreaterThanOrEqual(3)
    },
  )

  it.each(TEXT_ON_OWN_LIGHT_BG_PAIRS)('%s atende 4.5:1 (texto normal, padrão de badge)', (_label, textToken, bgToken) => {
    const ratio = contrastRatio(tokens[textToken], tokens[bgToken])
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  // Regressão documentada do achado original: os tokens de PREENCHIMENTO
  // (--color-success/--color-warning) continuam abaixo de 4.5:1 no tema
  // claro — é esperado, porque eles não são mais usados como `text-*` (só
  // como fundo de badge/barra, ver SEVERITY_BG/SEVERITY_BAR em
  // visuals.ts). No tema escuro isso NÃO se repete por desenho: a Decisão 5
  // do ADR-071 escolheu tons de preenchimento mais claros/saturados no
  // escuro (ambos passam de 4.5:1 lá), então este bloco só roda no claro.
})

it.each([
  ['success', '--color-success'] as const,
  ['warning', '--color-warning'] as const,
])(
  '--color-%s (preenchimento) permanece abaixo de 4.5:1 no tema claro — não deve virar texto',
  (_name, tokenName) => {
    const ratio = contrastRatio(LIGHT_TOKENS[tokenName], LIGHT_BG.surface)
    expect(ratio).toBeLessThan(4.5)
  },
)

describe('--color-gray-400 — exceção conhecida (banida como texto por nome, não por valor calculado)', () => {
  // `colorContrast.test.tsx` já bane `text-gray-400`/`border-gray-400`/
  // `placeholder-gray-400` por nome de classe, nos dois temas (ADR-071
  // Decisão 7) — precisamente porque no tema claro o valor calculado
  // reprova 4.5:1 (pré-existente, não introduzido por este ADR).
  it('não atende 4.5:1 no tema claro contra --color-surface (por isso é banido por nome)', () => {
    const ratio = contrastRatio(LIGHT_TOKENS['--color-gray-400'], LIGHT_BG.surface)
    expect(ratio).toBeLessThan(4.5)
  })

  it('atende 4.5:1 no tema escuro contra --color-surface (ADR-071 Decisão 4) — mesmo assim continua banido como texto por nome, regra igual nos dois temas', () => {
    const ratio = contrastRatio(DARK_TOKENS['--color-gray-400'], DARK_BG.surface)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })
})
