import { describe, expect, it } from 'vitest'
import {
  classifyExplanationErrorStatus,
  explanationSourceLabel,
  parseLatestExplanation,
} from './explanation-contracts'

function buildPayload(overrides: Record<string, unknown> = {}) {
  return {
    plant_id: '11111111-1111-1111-1111-111111111111',
    status: 'ATTENTION',
    source: 'AI_ASSISTED',
    summary: 'Produção abaixo do esperado nos últimos dias.',
    what_it_means: 'O ciclo está em atenção por causa de energia importada acima do previsto.',
    next_steps: ['Revisar consumo importado', 'Acompanhar os próximos dias'],
    disclaimer:
      'Explicação informativa baseada apenas nos diagnósticos calculados pelo Mplacas; não confirma causa técnica nem substitui inspeção profissional.',
    evidence_codes: ['IMPORTED_ENERGY_HIGH'],
    ...overrides,
  }
}

describe('parseLatestExplanation', () => {
  it('faz parse de um payload válido com origem AI_ASSISTED', () => {
    const result = parseLatestExplanation(buildPayload())
    expect(result).toEqual({
      plant_id: '11111111-1111-1111-1111-111111111111',
      status: 'ATTENTION',
      source: 'AI_ASSISTED',
      summary: 'Produção abaixo do esperado nos últimos dias.',
      what_it_means: 'O ciclo está em atenção por causa de energia importada acima do previsto.',
      next_steps: ['Revisar consumo importado', 'Acompanhar os próximos dias'],
      disclaimer:
        'Explicação informativa baseada apenas nos diagnósticos calculados pelo Mplacas; não confirma causa técnica nem substitui inspeção profissional.',
      evidence_codes: ['IMPORTED_ENERGY_HIGH'],
    })
  })

  it('faz parse de um payload válido com origem DETERMINISTIC (provedor de IA não configurado ou indisponível)', () => {
    const result = parseLatestExplanation(
      buildPayload({
        source: 'DETERMINISTIC',
        evidence_codes: ['NO_ACTIVE_DIAGNOSTIC'],
        next_steps: ['Manter o acompanhamento periódico dos indicadores energéticos.'],
      })
    )
    expect(result.source).toBe('DETERMINISTIC')
    expect(result.evidence_codes).toEqual(['NO_ACTIVE_DIAGNOSTIC'])
  })

  it('lança para payload que não é um objeto', () => {
    expect(() => parseLatestExplanation(null)).toThrow()
    expect(() => parseLatestExplanation('oops')).toThrow()
    expect(() => parseLatestExplanation(42)).toThrow()
  })

  it('lança quando um campo obrigatório está ausente ou com tipo errado (payload malformado)', () => {
    const missingSummary = buildPayload()
    delete (missingSummary as Record<string, unknown>).summary
    expect(() => parseLatestExplanation(missingSummary)).toThrow()

    expect(() => parseLatestExplanation(buildPayload({ next_steps: 'não é lista' }))).toThrow()
    expect(() => parseLatestExplanation(buildPayload({ evidence_codes: [1, 2] }))).toThrow()
  })

  it('lança para um source fora do vocabulário conhecido', () => {
    expect(() => parseLatestExplanation(buildPayload({ source: 'GUESSED' }))).toThrow()
  })
})

// Segundo teste obrigatório do §2.2 ("campo nulo/indisponível"): este payload
// não tem campo nulo dentro de um 200 (todos os campos são garantidos
// não-vazios pelo backend, ver comentário do arquivo de contrato) — a forma
// real de indisponibilidade do endpoint é o status HTTP 404
// (`EnergyCycleNotFoundError`, nenhuma fatura confirmada ainda). Cobrir esse
// status é o equivalente correto do caso "campo indisponível" para este
// contrato específico.
describe('classifyExplanationErrorStatus', () => {
  it('classifica 404 como indisponível (nenhum ciclo confirmado ainda, estado esperado)', () => {
    expect(classifyExplanationErrorStatus(404)).toBe('NOT_FOUND')
  })

  it('classifica 5xx como erro de servidor', () => {
    expect(classifyExplanationErrorStatus(500)).toBe('SERVER_ERROR')
    expect(classifyExplanationErrorStatus(503)).toBe('SERVER_ERROR')
  })

  it('devolve null para 401 (apiFetch já tentou refresh; nada a comunicar aqui)', () => {
    expect(classifyExplanationErrorStatus(401)).toBeNull()
  })
})

describe('explanationSourceLabel', () => {
  it('rotula AI_ASSISTED e DETERMINISTIC de forma distinta e nunca implícita', () => {
    expect(explanationSourceLabel('AI_ASSISTED')).toBe('Interpretação assistida por IA')
    expect(explanationSourceLabel('DETERMINISTIC')).toBe('Resumo determinístico do sistema')
  })
})
