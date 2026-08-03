import { describe, expect, it } from 'vitest'

// `text-gray-400` (#9ca3af) sobre fundo branco tem contraste ~2.85:1 — reprova
// WCAG AA para texto normal (mínimo 4.5:1). Este teste varre o código-fonte de
// todos os componentes e páginas do app e falha se a classe reaparecer,
// prevenindo regressão futura desse problema de acessibilidade (ver skill
// frontend-design). Usa `import.meta.glob` com `query: '?raw'` em vez de
// `node:fs` para não exigir `@types/node` (não instalado neste projeto) e
// continuar funcionando tanto no Vitest quanto no `vite build`/`tsc -b`.
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

describe('contraste de cor — sem text-gray-400 em componente algum', () => {
  it.each(files)('%s não usa a classe text-gray-400', (_path, content) => {
    expect(content).not.toMatch(/text-gray-400\b/)
  })
})
