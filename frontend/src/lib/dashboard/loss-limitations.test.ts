import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { KNOWN_ENGINE_LIMITATIONS, limitationInPortuguese } from './loss-limitations'

// Guarda contra texto do motor em inglês na tela (ADR-083, etapa 3): toda
// limitação escrita em `loss_taxonomy.py` precisa ter tradução aqui. Uma frase
// nova no backend sem tradução não quebra a tela (some), mas quebra este teste.
const TAXONOMY = resolve(__dirname, '../../../../src/mplacas/photovoltaic/loss_taxonomy.py')

function engineLimitations(): string[] {
  const source = readFileSync(TAXONOMY, 'utf-8')
  return [...source.matchAll(/^\s+"([a-z][^"]+)",?$/gm)].map((match) => match[1])
}

describe('limitationInPortuguese', () => {
  it('toda limitação do motor tem tradução', () => {
    const fromEngine = engineLimitations()
    expect(fromEngine.length).toBeGreaterThan(5)
    for (const limitation of fromEngine) {
      expect(KNOWN_ENGINE_LIMITATIONS).toContain(limitation)
    }
  })

  it('traduz uma frase conhecida e esconde uma desconhecida', () => {
    expect(limitationInPortuguese('interval operating states are unavailable')).toBe(
      'Não há registro do estado de operação ao longo do dia.',
    )
    expect(limitationInPortuguese('unknown caveat')).toBeNull()
    expect(limitationInPortuguese(null)).toBeNull()
  })
})
