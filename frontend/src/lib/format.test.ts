import { describe, expect, it } from 'vitest'
import { formatCycleLabel } from './format'

describe('formatCycleLabel', () => {
  it('converte AAAA-MM em mês abreviado em português + ano de 2 dígitos', () => {
    expect(formatCycleLabel('2026-07')).toBe('jul/26')
    expect(formatCycleLabel('2025-01')).toBe('jan/25')
    expect(formatCycleLabel('2024-12')).toBe('dez/24')
  })

  it('devolve a string crua como fallback para formato malformado', () => {
    expect(formatCycleLabel('2026-13')).toBe('2026-13')
    expect(formatCycleLabel('não é uma data')).toBe('não é uma data')
    expect(formatCycleLabel('2026-7')).toBe('2026-7')
    expect(formatCycleLabel('')).toBe('')
  })
})
