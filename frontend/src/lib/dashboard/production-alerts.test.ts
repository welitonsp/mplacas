import { describe, expect, it } from 'vitest'
import type { AnomalyDailyPoint } from './contracts'
import { calendarWindow, compareProductionAverageTrend, productionAlertSignal } from './production-alerts'

function day(date: string, kwh: number): AnomalyDailyPoint {
  return { date, actual_production_kwh: kwh, expected_production_kwh: null, level: null } as AnomalyDailyPoint
}

function range(startIso: string, count: number, kwh: number): AnomalyDailyPoint[] {
  const [y, m, d] = startIso.split('-').map(Number)
  return Array.from({ length: count }, (_, index) =>
    day(new Date(Date.UTC(y, m - 1, d + index)).toISOString().slice(0, 10), kwh),
  )
}

describe('calendarWindow (ADR-083, etapa 3)', () => {
  // O backend omite dias sem leitura: aqui faltam 17, 18 e 19/10.
  const withGap = [...range('2026-10-10', 7, 25), ...range('2026-10-20', 3, 25)]

  it('7 dias de calendário até o último dia presente, não as 7 últimas entradas', () => {
    expect(calendarWindow(withGap, 7).map((point) => point.date)).toEqual([
      '2026-10-16',
      '2026-10-20',
      '2026-10-21',
      '2026-10-22',
    ])
  })

  it('a semana anterior é a janela recuada 7 dias, também por calendário', () => {
    expect(calendarWindow(withGap, 7, 7).map((point) => point.date)).toEqual([
      '2026-10-10',
      '2026-10-11',
      '2026-10-12',
      '2026-10-13',
      '2026-10-14',
      '2026-10-15',
    ])
  })

  it('série vazia: janela vazia', () => {
    expect(calendarWindow([], 7)).toEqual([])
  })
})

describe('productionAlertSignal por calendário', () => {
  it('queda real de uma semana para outra dispara alerta', () => {
    const daily = [...range('2026-10-09', 7, 30), ...range('2026-10-16', 7, 15)]
    expect(productionAlertSignal(daily).tone).toBe('danger')
  })

  it('semana anterior inteira sem leitura: não compara (sem alarme fabricado)', () => {
    const daily = [...range('2026-10-02', 7, 30), ...range('2026-10-16', 7, 15)]
    expect(productionAlertSignal(daily).tone).toBe('neutral')
  })

  it('semana anterior com só 1 ou 2 dias de leitura: não compara (média de 1 dia não vale por 7)', () => {
    const daily = [...range('2026-10-14', 2, 30), ...range('2026-10-16', 7, 15)]
    expect(productionAlertSignal(daily).tone).toBe('neutral')
  })
})

describe('compareProductionAverageTrend por calendário', () => {
  it('janela anterior com menos de 3 dias: "Sem comparação"', () => {
    const daily = [...range('2026-10-14', 2, 30), ...range('2026-10-16', 7, 15)]
    expect(compareProductionAverageTrend(daily, 7).percent).toBeNull()
  })

  it('com 3 dias ou mais nas duas janelas, compara', () => {
    const daily = [...range('2026-10-12', 3, 30), ...range('2026-10-16', 7, 15)]
    expect(compareProductionAverageTrend(daily, 7).percent).toBeCloseTo(-50)
  })
})
