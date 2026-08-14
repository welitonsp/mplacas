import { describe, expect, it } from 'vitest'

// Guarda estática prometida pelo plano T7 (2026-08-13, mesmo modelo de
// `no-client-computed-relative-to-own-median-deviation.test.ts`).
//
// `computeYieldStats`/`YIELD_ATYPICAL_THRESHOLD_PERCENT` viviam em
// `frontend/src/lib/dashboard/yield.ts` (arquivo removido nesta correção de
// rota) e calculavam, por dia, `((yieldValue - periodYield) / periodYield) *
// 100` — algebricamente `(razão − 1) × 100`, a mesma forma já catalogada
// como cálculo de domínio (desloca o ponto de referência do zero), não
// conversão de unidade (o precedente legítimo de reescala pura,
// `photovoltaic-contracts.ts::ratioToPercent`, só faz `x × 100`). O limiar
// de severidade (`YIELD_ATYPICAL_THRESHOLD_PERCENT = 20`) também vivia no
// frontend, calibrado em dois casos reais desta usina — regra de negócio,
// não apresentação.
//
// O cálculo foi movido para `intelligence/anomaly_service.py::
// _compute_period_yield`/`_yield_deviation_from_median_percent`, que agora
// expõe `yield_kwh_per_kwh_m2`/`yield_deviation_from_median_percent` por dia
// e `period_yield_kwh_per_kwh_m2`/`yield_atypical_threshold_percent` no
// envelope de `GET /energy/anomalies/latest` — `contracts.ts` só valida
// forma, `YieldCard.tsx`/`ProductionHistoryChart.tsx` só formatam.
//
// Duas frentes, como o resto deste teste explica:
const sourceFiles = import.meta.glob('/src/**/*.{ts,tsx}', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

function sourceOf(pathSuffix: string): string {
  const path = Object.keys(sourceFiles).find((candidate) => candidate.endsWith(pathSuffix))
  const source = path !== undefined ? sourceFiles[path] : undefined
  if (source === undefined) {
    throw new Error(`guarda não encontrou o arquivo esperado: ${pathSuffix}`)
  }
  return source
}

// Insensível a espaço em branco: cobre `- 1)`, `-1)`, `*  100`, `*100` etc.
const FORBIDDEN_WHITESPACE_INSENSITIVE_SUBSTRINGS = ['-1)', '*100']

describe('nenhum cálculo de rendimento/desvio de período é reintroduzido no cliente (plano T7)', () => {
  it('a guarda continua lendo os arquivos reais, não vira no-op silencioso', () => {
    expect(() => sourceOf('/lib/dashboard/contracts.ts')).not.toThrow()
    expect(() => sourceOf('/components/YieldCard.tsx')).not.toThrow()
  })

  // Frente 1: os identificadores removidos de `yield.ts` são específicos o
  // bastante para nunca aparecer por acaso em nenhum outro contexto — uma
  // varredura em toda `src/` (mesmo padrão de
  // `no-client-computed-expected-production.test.ts`) cobre reintrodução em
  // QUALQUER arquivo, incluindo um novo `yield.ts` recriado do zero.
  //
  // Regex, não substring crua: os comentários deste próprio teste e de
  // `contracts.ts` citam os dois nomes em prosa, por proveniência histórica
  // (mesmo padrão de `device-contracts.ts` citando `relativeToMedianPercent`
  // removida) — uma checagem de substring pegaria a própria explicação.
  // `computeYieldStats(` cobre declaração (`function computeYieldStats(`)
  // e chamada/import; `const YIELD_ATYPICAL_THRESHOLD_PERCENT` cobre
  // (re)declaração do limiar. Arquivos `.test.ts(x)` também ficam de fora,
  // mesma exclusão de `no-client-computed-expected-production.test.ts`.
  const COMPUTE_YIELD_STATS_USAGE = /\bcomputeYieldStats\s*\(/
  const YIELD_THRESHOLD_DECLARATION = /\bconst\s+YIELD_ATYPICAL_THRESHOLD_PERCENT\b/

  it('`computeYieldStats`/`YIELD_ATYPICAL_THRESHOLD_PERCENT` não são declarados/chamados em nenhum arquivo de `src/`', () => {
    const offenders = Object.entries(sourceFiles)
      .filter(([path]) => !path.endsWith('.test.ts') && !path.endsWith('.test.tsx'))
      .filter(
        ([, content]) =>
          COMPUTE_YIELD_STATS_USAGE.test(content) || YIELD_THRESHOLD_DECLARATION.test(content)
      )
      .map(([path]) => path)

    expect(offenders).toEqual([])
  })

  // Frente 2: os dois arquivos onde o valor pronto do backend chega e é
  // consumido — mais prováveis de ganhar de volta um "cálculo rápido" ad hoc
  // mesmo sem reintroduzir os identificadores antigos.
  it('`contracts.ts` não contém `(r - 1)` nem `* 100` (nem variações de espaçamento)', () => {
    const collapsed = sourceOf('/lib/dashboard/contracts.ts').replace(/\s+/g, '')
    const offenders = FORBIDDEN_WHITESPACE_INSENSITIVE_SUBSTRINGS.filter((forbidden) =>
      collapsed.includes(forbidden)
    )
    expect(offenders).toEqual([])
  })

  it('`YieldCard.tsx` não contém `(r - 1)` nem `* 100` (nem variações de espaçamento)', () => {
    const collapsed = sourceOf('/components/YieldCard.tsx').replace(/\s+/g, '')
    const offenders = FORBIDDEN_WHITESPACE_INSENSITIVE_SUBSTRINGS.filter((forbidden) =>
      collapsed.includes(forbidden)
    )
    expect(offenders).toEqual([])
  })

  // Frente 3 — catraca para `ProductionHistoryChart.tsx` (T7c).
  //
  // A versão anterior desta guarda ISENTAVA este arquivo da varredura, com a
  // justificativa de que ele já continha `* 100` legítimos (posicionamento em
  // pixel) que virariam ruído. O efeito colateral era pior que o ruído: o
  // arquivo contém as duas violações reais que o parecer de domínio apontou —
  // `performancePercent` (composição de kWh no cliente, ~:103-112) e
  // `activeAverageDeltaPercent` (`(atual − média) ÷ média × 100`, ~:124-127) —
  // e a isenção garantia que elas nunca seriam pegas. Uma guarda com carve-out
  // no único lugar onde a violação existe não é guarda.
  //
  // Em vez de exigir zero (o que quebraria de imediato e seria revertido) ou
  // isentar (o que não protege nada), esta catraca **congela a dívida
  // conhecida**: o número atual é o teto. Corrigir reduz e o teste avisa para
  // baixar o teto; introduzir um cálculo novo aumenta e o teste falha.
  //
  // Contagem levantada em 2026-08-13. `*100` inclui usos legítimos de
  // percentual de posicionamento SVG; `-1)` inclui indexação de array. Por isso
  // a catraca é sobre a CONTAGEM, não sobre a presença — presença zero não é
  // alcançável aqui sem mover o cálculo para o backend, que é trabalho próprio.
  const CHART_KNOWN_DEBT = { percentMultiplications: 6, minusOneExpressions: 2 } as const

  it('`ProductionHistoryChart.tsx` não ganha aritmética de grandeza física nova (catraca)', () => {
    const collapsed = sourceOf('/components/ProductionHistoryChart.tsx').replace(/\s+/g, '')
    const percentMultiplications = (collapsed.match(/\*100(?!\d)/g) ?? []).length
    const minusOneExpressions = (collapsed.match(/-1\)/g) ?? []).length

    expect({ percentMultiplications, minusOneExpressions }).toEqual(CHART_KNOWN_DEBT)
  })
})
