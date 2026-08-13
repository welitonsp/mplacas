import { describe, expect, it } from 'vitest'

// Guarda de classe para alvo de toque (WCAG 2.5.8 / padrão de 44px do projeto).
//
// Por que ela existe: a tarefa T10 declarou ter "eliminado a classe do
// problema" tendo corrigido apenas os `<select>`. Ficaram SEIS botões abaixo do
// mínimo — incluindo `RefreshBar.tsx`, que a própria T10 citou como referência
// de padrão correto, e `EpisodeTimelineSection.tsx`, criado horas depois já
// fora do padrão. Correção pontual não impede a próxima ocorrência; esta
// varredura impede.
//
// Lê o texto-fonte via `import.meta.glob` do Vite, mesma técnica das demais
// guardas estáticas do projeto.
const sourceFiles = import.meta.glob('/src/**/*.tsx', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

const PRODUCTION_SOURCES = Object.entries(sourceFiles).filter(
  ([path]) => !path.endsWith('.test.tsx')
)

// Casa qualquer `min-h-[Npx]` com N < 44 (dois dígitos, 10–43).
const BELOW_MINIMUM = /min-h-\[(?:[1-3][0-9]|4[0-3])px\]/g

describe('alvo de toque mínimo de 44px (WCAG 2.5.8)', () => {
  // Sem esta asserção a guarda vira no-op silencioso se o glob deixar de casar
  // — o mesmo erro que já derrubou uma guarda anterior desta sessão.
  it('a guarda está lendo os arquivos reais de componente', () => {
    expect(PRODUCTION_SOURCES.length).toBeGreaterThan(20)
  })

  it('nenhum componente declara alvo de toque abaixo de 44px', () => {
    const offenders = PRODUCTION_SOURCES.flatMap(([path, content]) => {
      const matches = content.match(BELOW_MINIMUM) ?? []
      return matches.map((match) => `${path}: ${match}`)
    })

    expect(offenders).toEqual([])
  })
})
