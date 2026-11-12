import { describe, expect, it } from 'vitest'
import { parseHomeCycles } from './home-cycles-contract'
import { parseMonthlyProductionHistory } from './monthly-history-contracts'
import { monthlyHistoryPayload } from '../../test/dashboardFixtures'

describe('parseHomeCycles', () => {
  it('lê só mês, fim do ciclo e três campos da conferência', () => {
    const cycles = parseHomeCycles({
      cycles: [
        {
          reference_month: '2026-09',
          cycle_end: '2026-09-14',
          utility_check: { verdict: 'LOSS', missing_credits_kwh: '12.50', loss_confirmed: true },
        },
      ],
    })
    expect(cycles).toEqual([
      { referenceMonth: '2026-09', cycleEnd: '2026-09-14', check: { verdict: 'LOSS', missingCreditsKwh: 12.5, lossConfirmed: true } },
    ])
  })

  it('conferência ausente fica null; veredito novo vira UNVERIFIABLE; valor ilegível vira null, nunca 0', () => {
    const [semConferencia, novo] = parseHomeCycles({
      cycles: [
        { reference_month: '2026-08', cycle_end: null },
        { reference_month: '2026-09', utility_check: { verdict: 'NOVO', missing_credits_kwh: 'abc' } },
      ],
    })
    expect(semConferencia).toEqual({ referenceMonth: '2026-08', cycleEnd: null, check: null })
    expect(novo.check).toEqual({ verdict: 'UNVERIFIABLE', missingCreditsKwh: null, lossConfirmed: false })
  })

  it('forma inesperada lança', () => {
    expect(() => parseHomeCycles(null)).toThrow()
    expect(() => parseHomeCycles({ cycles: 'x' })).toThrow()
    expect(() => parseHomeCycles({ cycles: [{ reference_month: 'setembro' }] })).toThrow()
  })

  it('concorda com o parser completo do histórico mensal nos campos que usa', () => {
    const full = parseMonthlyProductionHistory(monthlyHistoryPayload)
    const small = parseHomeCycles(monthlyHistoryPayload)
    expect(small.map((c) => [c.referenceMonth, c.cycleEnd, c.check?.verdict ?? null])).toEqual(
      full.cycles.map((c) => [c.referenceMonth, c.cycleEnd, c.utilityCheck?.verdict ?? null]),
    )
  })
})
