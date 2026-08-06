import { describe, expect, it } from 'vitest'
import * as photovoltaicContracts from './photovoltaic-contracts'
// Import bruto do texto-fonte via sufixo `?raw` do Vite (tipado por
// `vite/client`, ver `src/vite-env.d.ts`) — evita depender de `node:fs`, que
// exigiria adicionar `@types/node` só para este teste.
import photovoltaicContractsSource from './photovoltaic-contracts.ts?raw'

// Critério de aceite mecânico #2 do ADR-068 (seção 7): depois da Etapa C,
// `photovoltaic-contracts.ts` não pode voltar a compor grandezas energéticas
// no cliente — a produção esperada é calculada inteiramente no backend
// (`photovoltaic/expected_production.py`) e o arquivo só estrutura os campos
// já prontos que o servidor devolve.

describe('photovoltaic-contracts.ts não compõe grandezas energéticas (ADR-068, seção 7)', () => {
  it('não exporta mais deriveExpectedDailyProduction', () => {
    expect('deriveExpectedDailyProduction' in photovoltaicContracts).toBe(false)
  })

  it('não contém multiplicação envolvendo dc_capacity_kwp, clear_sky_poa ou performance_ratio', () => {
    // Única exceção permitida: `ratioToPercent`, que converte uma razão
    // adimensional 0–1 para 0–100 multiplicando por 100 (`numeric * 100`).
    // Não é composição de grandezas físicas distintas — é conversão de
    // unidade de um único valor — então essa linha é explicitamente
    // descontada antes de procurar por multiplicações envolvendo as
    // grandezas físicas proibidas no restante do arquivo.
    const RATIO_TO_PERCENT_EXCEPTION = 'numeric * 100'
    expect(photovoltaicContractsSource).toContain(RATIO_TO_PERCENT_EXCEPTION)
    const contentWithoutException = photovoltaicContractsSource
      .split(RATIO_TO_PERCENT_EXCEPTION)
      .join('')

    const forbiddenTerms = ['dc_capacity_kwp', 'clear_sky_poa', 'performance_ratio']
    for (const term of forbiddenTerms) {
      const linesWithTerm = contentWithoutException
        .split('\n')
        .filter((line: string) => line.includes(term) && line.includes('*'))
      expect(linesWithTerm).toEqual([])
    }
  })
})
