import { describe, expect, it } from 'vitest'

// Cálculo real de contraste WCAG 2.2 (fórmula de luminância relativa, não um
// número hardcoded) — ver Etapa 1.1 do roteiro de UI/UX
// (docs/UI_UX_IMPLEMENTATION_ROADMAP_2026-08-04.md) e a medição original em
// docs/UI_UX_AUDIT_2026-08-04.md (P1-03).
//
// Os hex abaixo espelham literalmente os tokens declarados em `src/index.css`
// (mesmo padrão de `GRID_HEX` em `lib/dashboard/visuals.ts`: uma cópia
// documentada, não uma leitura em runtime do CSS — `import.meta.glob(...,
// { query: '?raw' })` não funciona para `.css` neste projeto porque o
// Vitest intercepta e mocka todo import de `.css`, inclusive com `?raw`,
// antes mesmo de o Vite processar a query — verificado experimentalmente).
// Se um destes hex mudar em `index.css`, ele PRECISA mudar aqui também — é
// exatamente o tipo de deriva que este teste deve pegar: se o valor não for
// atualizado dos dois lados, o índice fica correto mas divorciado do CSS
// real, e a próxima alteração de paleta que reintroduzir uma falha de AA
// ainda vai estourar aqui porque o cálculo é feito de verdade, não apenas
// declarado como "ok".
const TOKENS = {
  '--color-success-text': '#15803d',
  '--color-warning-text': '#b45309',
  '--color-danger-text': '#b91c1c',
  '--color-danger': '#dc2626',
  '--color-success': '#16a34a',
  '--color-warning': '#d97706',
  '--color-chart-reference': '#6b7280',
} as const

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

const WHITE = '#ffffff'

describe('contraste WCAG 2.2 — calculado por fórmula (luminância relativa), não hardcoded', () => {
  // Texto normal exige 4.5:1 (WCAG 1.4.3 AA). Estes são exatamente os pares
  // que reprovavam na auditoria original (--color-success/--color-warning
  // usados como texto), agora substituídos pelos tokens -text em SEVERITY_TEXT.
  it.each([
    ['--color-success-text', TOKENS['--color-success-text'], WHITE],
    ['--color-warning-text', TOKENS['--color-warning-text'], WHITE],
    ['--color-danger-text', TOKENS['--color-danger-text'], WHITE],
  ])('%s sobre branco atende 4.5:1 (texto normal, WCAG 1.4.3 AA)', (_name, foreground, background) => {
    const ratio = contrastRatio(foreground, background)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  // Elemento gráfico (linha/borda que carrega informação) exige 3:1
  // (WCAG 1.4.11) — é o token que substituiu `border-gray-400` na linha de
  // referência "Esperado" do gráfico de produção diária.
  it('--color-chart-reference sobre branco atende 3:1 (elemento gráfico, WCAG 1.4.11)', () => {
    const ratio = contrastRatio(TOKENS['--color-chart-reference'], WHITE)
    expect(ratio).toBeGreaterThanOrEqual(3)
  })

  // Regressão documentada do achado original: os tokens de PREENCHIMENTO
  // (--color-success/--color-warning) continuam abaixo de 4.5:1 — é esperado,
  // porque eles não são mais usados como `text-*` (só como fundo de badge/
  // barra — ver SEVERITY_BG/SEVERITY_BAR em visuals.ts, que continuam
  // intocados). Se algum componente voltar a usar `--color-success` como cor
  // de texto, é a variante `-text` (testada acima) que deve ser usada.
  it.each([
    ['--color-success', TOKENS['--color-success']],
    ['--color-warning', TOKENS['--color-warning']],
  ])('%s (preenchimento) permanece abaixo de 4.5:1 — não deve virar texto', (_name, foreground) => {
    const ratio = contrastRatio(foreground, WHITE)
    expect(ratio).toBeLessThan(4.5)
  })
})
