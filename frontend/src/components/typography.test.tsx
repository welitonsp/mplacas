import { describe, expect, it } from 'vitest'

// Etapa 1.5 do roteiro de UI/UX: piso de 12px para qualquer texto legível —
// `text-[10px]`/`text-[11px]` foram eliminados em favor da escala já
// tokenizada do Tailwind (`text-xs` = 12px). Este teste varre o código-fonte
// de todos os componentes e páginas e falha se um tamanho arbitrário abaixo
// de 12px reaparecer (mesmo padrão de `colorContrast.test.tsx`).
// `./*.tsx` (não recursivo) não alcançava `components/charts/*.tsx` nem
// nenhuma outra subpasta de `components/` — mesmo tipo de bug que
// `colorContrast.test.tsx` já teve corrigido para `components/charts/` na
// Fase 0 do dark mode (ADR-071); nunca tinha sido replicado aqui. Corrigido
// para `**/*.tsx` (revisão final do dark mode, ADR-071 Fase 4).
const componentSources = import.meta.glob('./**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
// `../pages/*.tsx` (não recursivo) não alcançava `src/pages/dashboard/*.tsx`
// — os 4 módulos do painel (`OverviewPage`, `ProductionPage`, `FinancialPage`,
// `TechnicalPage`, ver ADR-072) ficaram fora deste guard desde que foram
// criados. Corrigido para `**/*.tsx` (mesma correção aplicada em
// `colorContrast.test.tsx`, ADR-072 Etapa 6).
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

// Casa qualquer `text-[Npx]` com N < 12 (1 ou 2 dígitos apenas, para não
// capturar `text-[12px]`+ por engano).
//
// Flag `g` + `matchAll`: a versão anterior usava `content.match` sem `g`, que
// só olha a PRIMEIRA ocorrência do arquivo. Um `text-[13px]` no topo escondia
// qualquer `text-[11px]` abaixo — foi assim que três rótulos de 11 px
// (`ProductionHistoryChart`, `HomeWeekCard`) passaram pelo guard
// (auditoria visual de 28/10/2026).
const ARBITRARY_TEXT_SIZE = /text-\[(\d{1,2})px\]/g

describe('tipografia — nenhum tamanho de texto arbitrário abaixo do piso de 12px', () => {
  it.each(files)('%s não usa text-[Npx] com N < 12', (_path, content) => {
    const belowFloor = [...content.matchAll(ARBITRARY_TEXT_SIZE)]
      .map((match) => Number(match[1]))
      .filter((size) => size < 12)
    expect(belowFloor).toEqual([])
  })
})
