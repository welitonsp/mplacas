import { describe, expect, it } from 'vitest'

// Guarda estática citada por `episodes.ts` (ADR-075, Decisão 4.2). O
// agrupamento de episódios é estrutura — agrupar por código, contar dias de
// calendário, escolher o dia mais severo por `LEVEL_RANK` — e não pode virar
// porta de entrada para cálculo de grandeza física no cliente.
//
// O projeto já teve duas violações dessa regra: `deriveExpectedDailyProduction`
// (auditoria de 2026-08-04) e `relativeToMedianPercent` (revisão de T1c), ambas
// introduzidas como "só uma conversãozinha". Por isso a guarda existe desde o
// primeiro commit deste módulo, não depois do terceiro incidente.
//
// Lê o texto-fonte via `import.meta.glob` do Vite (mesma técnica de
// `no-client-computed-expected-production.test.ts`), com espaço em branco
// removido antes da busca, para que reformatar não escape da varredura. Por
// isso os comentários DESTE arquivo usam "−"/"×" tipográficos ao citar as
// formas proibidas em prosa.
const sourceFiles = import.meta.glob('/src/lib/dashboard/episodes.ts', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

const GUARDED_PATH = Object.keys(sourceFiles).find((path) => path.endsWith('episodes.ts'))
const GUARDED_SOURCE = GUARDED_PATH ? sourceFiles[GUARDED_PATH] : undefined

// Insensível a espaço, mas COM fronteira de dígito. A primeira versão desta
// guarda usava a substring crua `*100` e acusava falso positivo em
// `24 * 60 * 60 * 1000` (a constante de um dia em `isNextCalendarDay`), porque
// `*100` é prefixo de `*1000`. Uma guarda que grita no lugar errado é tão
// inútil quanto uma que não grita: `(?!\d)` exige que o número termine ali.
const FORBIDDEN_PATTERNS: ReadonlyArray<{ label: string; pattern: RegExp }> = [
  { label: '(razão − 1)', pattern: /-1\)/ },
  { label: '× 100', pattern: /\*100(?!\d)/ },
  { label: '÷ 100', pattern: /\/100(?!\d)/ },
]

describe('nenhum cálculo de grandeza física é introduzido em episodes.ts (ADR-075)', () => {
  // Sem esta asserção a guarda vira no-op silencioso caso o arquivo seja
  // movido ou renomeado — o glob simplesmente não casaria e as demais
  // asserções passariam sobre uma string vazia.
  it('o arquivo continua existindo e sendo lido pela guarda', () => {
    expect(GUARDED_PATH).toBeDefined()
    expect(GUARDED_SOURCE).toBeDefined()
    expect((GUARDED_SOURCE ?? '').length).toBeGreaterThan(0)
  })

  it('não contém aritmética de percentual nem de razão', () => {
    const collapsed = (GUARDED_SOURCE ?? '').replace(/\s+/g, '')
    const offenders = FORBIDDEN_PATTERNS.filter(({ pattern }) => pattern.test(collapsed)).map(
      ({ label }) => label
    )
    expect(offenders).toEqual([])
  })

  // A única aritmética legítima do módulo é a de calendário — a constante de
  // milissegundos de um dia em `isNextCalendarDay`. Qualquer outra multiplicação
  // é suspeita, então esta asserção fixa que ela é a única.
  it('a única multiplicação do arquivo é a constante de um dia em milissegundos', () => {
    const multiplications = ((GUARDED_SOURCE ?? '').match(/\*/g) ?? []).length
    expect(multiplications).toBe(3) // 24 * 60 * 60 * 1000
  })

  it('não recalcula severidade a partir de limiar numérico', () => {
    // O nível vem pronto do backend (`diagnostic.level`); comparar contra um
    // número aqui significaria reintroduzir limiar de severidade no cliente,
    // exatamente o que a T7 acabou de remover de `yield.ts`.
    expect(GUARDED_SOURCE ?? '').not.toMatch(/THRESHOLD/i)
  })
})
