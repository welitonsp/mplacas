import { describe, expect, it } from 'vitest'

// Guarda estática prometida pela seção "Validação" do ADR-074
// ("Teste que falha se algum cálculo for reintroduzido no cliente — o
// projeto já tem esse padrão em
// `no-client-computed-expected-production.test.ts`"), cumprida aqui para
// `device-contracts.ts` (revisão P1 independente de T1c, 2026-08-12).
//
// `relativeToMedianPercent` chegou a viver neste arquivo e computava
// `(razão − 1) × 100` a partir de `relative_to_own_median` — deslocar o
// ponto de referência do zero é cálculo de domínio, não conversão de
// unidade (o precedente legítimo, `photovoltaic-contracts.ts::
// ratioToPercent`, só faz `x × 100`, nunca `(x − k) × 100`). O cálculo foi
// movido para `devices/metrics.py::assess_devices`, que agora expõe
// `relative_to_own_median_deviation_percent` pronto; este arquivo só
// formata.
//
// Lê o texto-fonte via `import.meta.glob` do Vite (mesma técnica de
// `no-client-computed-expected-production.test.ts`), com todo espaço em
// branco removido antes de buscar — para que reformatar a expressão (quebra
// de linha, espaço extra, tab) não escape da guarda. Por isso os comentários
// deste próprio arquivo usam "−"/"×" tipográficos em vez de "-"/"*" ao citar
// a fórmula proibida em prosa.
const sourceFiles = import.meta.glob('/src/lib/dashboard/device-contracts.ts', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

const GUARDED_PATH = Object.keys(sourceFiles).find((path) => path.endsWith('device-contracts.ts'))
const GUARDED_SOURCE = GUARDED_PATH ? sourceFiles[GUARDED_PATH] : undefined

// Insensível a espaço em branco: cobre `- 1)`, `-1)`, `*  100`, `*100` etc.
const FORBIDDEN_WHITESPACE_INSENSITIVE_SUBSTRINGS = ['-1)', '*100']

describe('nenhum cálculo de razão→percentual é reintroduzido em device-contracts.ts (ADR-074)', () => {
  it('o arquivo continua existindo e sendo lido pela guarda', () => {
    expect(GUARDED_PATH).toBeDefined()
    expect(GUARDED_SOURCE).toBeDefined()
  })

  it('não contém `(r - 1)` nem `* 100` (nem variações de espaçamento) em device-contracts.ts', () => {
    const collapsed = (GUARDED_SOURCE ?? '').replace(/\s+/g, '')
    const offenders = FORBIDDEN_WHITESPACE_INSENSITIVE_SUBSTRINGS.filter((forbidden) =>
      collapsed.includes(forbidden)
    )
    expect(offenders).toEqual([])
  })

  it('não reexporta a função `relativeToMedianPercent` (removida nesta correção de rota) — só a cita em comentário explicativo', () => {
    expect(GUARDED_SOURCE ?? '').not.toMatch(/export\s+function\s+relativeToMedianPercent/)
  })
})
