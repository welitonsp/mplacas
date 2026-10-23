import { describe, expect, it } from 'vitest'
import type { AnomalyDailyPoint, Diagnostic } from './contracts'
import type { PlantSetup } from './plant-setup-contracts'
import { STALE_TELEMETRY_DAYS, buildCalmNote, buildHomeStatus, buildHomeTodos } from './home'

function day(date: string, actual: number | null, expected: number | null = null): AnomalyDailyPoint {
  return {
    date,
    actual_production_kwh: actual,
    expected_production_kwh: expected,
    level: expected == null ? null : 'NORMAL',
  } as AnomalyDailyPoint
}

// 14 dias de 26 kWh, sem esperado: o gatilho compara a última semana com a
// anterior (sem queda → "success").
function steadyFortnight(lastDay: string, kwh = 26): AnomalyDailyPoint[] {
  const end = new Date(`${lastDay}T12:00:00Z`)
  return Array.from({ length: 14 }, (_, index) => {
    const date = new Date(end)
    date.setUTCDate(end.getUTCDate() - (13 - index))
    return day(date.toISOString().slice(0, 10), kwh)
  })
}

const TODAY = new Date(2026, 9, 23, 9, 0) // 23/10/2026, horário local

describe('buildHomeStatus (ADR-083)', () => {
  it('sem nenhuma leitura ainda: aguarda, sem alarme', () => {
    const status = buildHomeStatus({ daily: [], latestDataDate: null, today: TODAY })
    expect(status.tone).toBe('neutral')
    expect(status.title).toBe('Aguardando a primeira leitura da usina')
  })

  it('leitura de ontem e produção estável: "funcionando bem" com o último dia', () => {
    const daily = steadyFortnight('2026-10-22')
    const status = buildHomeStatus({ daily, latestDataDate: '2026-10-22', today: TODAY })
    expect(status).toEqual({
      tone: 'success',
      title: 'Sua usina está funcionando bem',
      detail: 'Último dia: 26 kWh · dado de 22/10',
    })
  })

  it(`sem leitura há ${STALE_TELEMETRY_DAYS} dias: avisa falta de comunicação, não "produção baixa"`, () => {
    const daily = steadyFortnight('2026-10-20')
    const status = buildHomeStatus({ daily, latestDataDate: '2026-10-20', today: TODAY })
    expect(status.tone).toBe('warning')
    expect(status.title).toBe('Sem leitura da usina desde 20/10')
    expect(status.detail).toMatch(/internet/)
  })

  it('anteontem ainda não é falta de comunicação (atraso normal do provedor)', () => {
    const daily = steadyFortnight('2026-10-21')
    expect(buildHomeStatus({ daily, latestDataDate: '2026-10-21', today: TODAY }).tone).toBe('success')
  })

  it('queda forte contra a semana anterior: perigo, sugerindo conferir o tempo antes', () => {
    const daily = [...steadyFortnight('2026-10-15', 30).slice(0, 7), ...steadyFortnight('2026-10-22', 10).slice(7)]
    const status = buildHomeStatus({ daily, latestDataDate: '2026-10-22', today: TODAY })
    expect(status.tone).toBe('danger')
    expect(status.title).toBe('Produção bem abaixo do normal')
    expect(status.detail).toMatch(/tempo esteve bom/)
  })

  it('menos de 3 dias para comparar: "gerando", tom neutro', () => {
    const daily = [day('2026-10-22', 24.4)]
    const status = buildHomeStatus({ daily, latestDataDate: '2026-10-22', today: TODAY })
    expect(status.tone).toBe('neutral')
    expect(status.title).toBe('Sua usina está gerando')
    expect(status.detail).toBe('Último dia: 24,4 kWh · dado de 22/10')
  })
})

function setup(overrides: Partial<PlantSetup> = {}): PlantSetup {
  return { completed: 7, total: 7, pendingBills: 0, confirmedBills: 3, ...overrides } as PlantSetup
}

function diagnostic(severity: Diagnostic['severity'], code: string = severity): Diagnostic {
  return { code, severity, message: `msg ${code}`, recommended_action: `ação ${code}` }
}

describe('buildHomeTodos (ADR-083)', () => {
  it('cadastro completo, nada pendente e só avisos: lista vazia', () => {
    expect(buildHomeTodos({ setup: setup(), diagnostics: [diagnostic('WARNING'), diagnostic('INFO')] })).toEqual([])
  })

  it('cadastro incompleto e faturas pendentes viram tarefas, nesta ordem', () => {
    const todos = buildHomeTodos({ setup: setup({ completed: 5, pendingBills: 2 }), diagnostics: [] })
    expect(todos.map((todo) => [todo.title, todo.target])).toEqual([
      ['Completar o cadastro da usina', 'setup'],
      ['Conferir 2 faturas importadas', 'bills'],
    ])
    expect(todos[0].detail).toMatch(/^Faltam 2 itens \(5 de 7\)/)
  })

  it('singular quando falta 1 item ou há 1 fatura', () => {
    const todos = buildHomeTodos({ setup: setup({ completed: 6, pendingBills: 1 }), diagnostics: [] })
    expect(todos[0].detail).toMatch(/^Falta 1 item \(6 de 7\)/)
    expect(todos[1].title).toBe('Conferir 1 fatura importada')
  })

  it('só diagnóstico CRÍTICO vira tarefa, com a ação recomendada do motor', () => {
    const todos = buildHomeTodos({ setup: null, diagnostics: [diagnostic('WARNING'), diagnostic('CRITICAL', 'X1')] })
    expect(todos).toEqual([{ key: 'diagnostic-X1', title: 'msg X1', detail: 'ação X1', target: 'energy' }])
  })
})

describe('buildCalmNote (ADR-083)', () => {
  const clean = { missing_days: 0, unavailable_days: 0, provisional_days: 0, incomplete_days: 0 }

  it('ciclo completo: nada a explicar', () => {
    expect(buildCalmNote(clean, 'set/26')).toBeNull()
  })

  it('dia sem leitura: explica uma vez, sem pedir ação', () => {
    expect(buildCalmNote({ ...clean, missing_days: 1 }, 'set/26')).toBe(
      '1 dia do ciclo set/26 ficou sem leitura do inversor. Isso não muda a economia, que vem da fatura, e não precisa fazer nada.',
    )
  })

  it('dias sem leitura e em consolidação, no plural', () => {
    expect(buildCalmNote({ ...clean, missing_days: 1, unavailable_days: 1, provisional_days: 2 }, 'out/26')).toBe(
      '2 dias do ciclo out/26 ficaram sem leitura do inversor. 2 dias ainda estão sendo consolidados pelo provedor. Isso não muda a economia, que vem da fatura, e não precisa fazer nada.',
    )
  })
})
