import { describe, expect, it } from 'vitest'

// `text-gray-400` (#9ca3af) sobre fundo branco tem contraste ~2.85:1 — reprova
// WCAG AA para texto normal (mínimo 4.5:1). Este teste varre o código-fonte de
// todos os componentes e páginas do app e falha se a classe reaparecer,
// prevenindo regressão futura desse problema de acessibilidade (ver skill
// frontend-design). Usa `import.meta.glob` com `query: '?raw'` em vez de
// `node:fs` para não exigir `@types/node` (não instalado neste projeto) e
// continuar funcionando tanto no Vitest quanto no `vite build`/`tsc -b`.
const componentSources = import.meta.glob('./**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
// `../pages/*.tsx` (não recursivo) não alcançava `src/pages/dashboard/*.tsx`
// — os 4 módulos do painel (`OverviewPage`, `ProductionPage`, `FinancialPage`,
// `TechnicalPage`, ver ADR-072) ficaram fora deste guard desde que foram
// criados. Corrigido para `**/*.tsx` (mesmo tipo de correção já feita aqui
// para `components/charts/` na Fase 0 do dark mode, ADR-072 Etapa 6).
const pageSources = import.meta.glob('../pages/**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
// Nem `components/`/`pages/` cobrem tudo: `lib/dashboard/visuals.ts` é
// `.ts` puro (fora dos dois globs `.tsx` acima) mas guarda strings de classe
// Tailwind de verdade (`SEVERITY_TEXT`/`SEVERITY_BG`/etc.); `main.tsx`,
// `App.tsx` e `contexts/*.tsx` também podem carregar classe solta e ficavam
// fora de qualquer guard. Lista explícita (não um glob amplo em `../`, que
// pegaria `node_modules`/config) — revisão final do dark mode, ADR-071
// Fase 4.
const otherSources = import.meta.glob(
  ['../lib/dashboard/visuals.ts', '../main.tsx', '../App.tsx', '../contexts/*.tsx'],
  { query: '?raw', import: 'default', eager: true }
) as Record<string, string>

const files = Object.entries({ ...componentSources, ...pageSources, ...otherSources }).filter(
  ([path]) => !path.endsWith('.test.tsx')
)

describe('contraste de cor — sem text-gray-400 em componente algum', () => {
  it.each(files)('%s não usa a classe text-gray-400', (_path, content) => {
    expect(content).not.toMatch(/text-gray-400\b/)
  })
})

// `border-gray-400` (#9ca3af) sobre branco tem contraste ~2,54:1 — reprova o
// mínimo de 3:1 para elementos gráficos (WCAG 1.4.11). Era exatamente a linha
// de referência "Esperado" do gráfico (ver P1-03 na auditoria); agora usa
// `--color-chart-reference`. Guard de regressão análogo ao de `text-gray-400`
// acima.
describe('contraste de cor — sem border-gray-400 em componente algum', () => {
  it.each(files)('%s não usa a classe border-gray-400', (_path, content) => {
    expect(content).not.toMatch(/border-gray-400\b/)
  })
})

// `placeholder-gray-400` (#9ca3af) sobre fundo branco tem contraste ~2,85:1 —
// reprova WCAG AA para texto normal (mínimo 4.5:1), mesma falha medida nos
// placeholders de `LoginPage`/`CapexRegistrationForm`. Guard de regressão
// análogo aos de `text-gray-400`/`border-gray-400` acima.
describe('contraste de cor — sem placeholder-gray-400 em componente algum', () => {
  it.each(files)('%s não usa a classe placeholder-gray-400', (_path, content) => {
    expect(content).not.toMatch(/placeholder-gray-400\b/)
  })
})
