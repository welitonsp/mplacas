import { describe, expect, it } from 'vitest'

// Etapa 1.5 do roteiro de UI/UX: piso de 12px para qualquer texto legível —
// `text-[10px]`/`text-[11px]` foram eliminados em favor da escala já
// tokenizada do Tailwind (`text-xs` = 12px). Este teste varre o código-fonte
// de todos os componentes e páginas e falha se um tamanho arbitrário abaixo
// de 12px reaparecer (mesmo padrão de `colorContrast.test.tsx`).
const componentSources = import.meta.glob('./*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
const pageSources = import.meta.glob('../pages/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const files = Object.entries({ ...componentSources, ...pageSources }).filter(
  ([path]) => !path.endsWith('.test.tsx')
)

// Casa qualquer `text-[Npx]` com N < 12 (1 ou 2 dígitos apenas, para não
// capturar `text-[12px]`+ por engano).
const BELOW_FLOOR_ARBITRARY_TEXT_SIZE = /text-\[(\d{1,2})px\]/

describe('tipografia — nenhum tamanho de texto arbitrário abaixo do piso de 12px', () => {
  it.each(files)('%s não usa text-[Npx] com N < 12', (_path, content) => {
    const match = content.match(BELOW_FLOOR_ARBITRARY_TEXT_SIZE)
    if (match) {
      expect(Number(match[1])).toBeGreaterThanOrEqual(12)
    } else {
      expect(match).toBeNull()
    }
  })
})
