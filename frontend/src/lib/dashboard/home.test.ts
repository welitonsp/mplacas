import { describe, expect, it } from 'vitest'
import type { AnomalyDailyPoint, Diagnostic } from './contracts'
import type { HomeCycleSummary } from './home'
import type { PlantSetup } from './plant-setup-contracts'
import {
  BILL_REMINDER_AFTER_DAYS,
  STALE_TELEMETRY_DAYS,
  buildCalmNote,
  buildHomeStatus,
  buildHomeTodos,
  buildUnavailableHomeStatus,
  buildWeekWindow,
} from './home'

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
    const daily = [...steadyFortnight('2026-10-22', 30).slice(0, 7), ...steadyFortnight('2026-10-22', 10).slice(7)]
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

  it('só diagnóstico CRÍTICO vira tarefa, e abre a lista de diagnósticos do Início', () => {
    const todos = buildHomeTodos({ setup: null, diagnostics: [diagnostic('WARNING'), diagnostic('CRITICAL', 'INVERSOR')] })
    expect(todos).toHaveLength(1)
    expect(todos[0]).toMatchObject({ title: 'msg INVERSOR', detail: 'ação INVERSOR', target: 'diagnostics' })
    expect(todos[0].key).toBe(['diagnostic', 'INVERSOR'].join('-'))
  })

  it('lacuna de telemetria (MISSING_DAILY_DATA), mesmo CRÍTICA, não vira tarefa do dono', () => {
    expect(buildHomeTodos({ setup: setup(), diagnostics: [diagnostic('CRITICAL', 'MISSING_DAILY_DATA')] })).toEqual([])
  })
})

function cycle(overrides: Partial<HomeCycleSummary> = {}): HomeCycleSummary {
  return { referenceMonth: '2026-09', cycleEnd: '2026-09-14', check: null, ...overrides }
}

function withCheck(
  verdict: NonNullable<HomeCycleSummary['check']>['verdict'],
  extra: Partial<NonNullable<HomeCycleSummary['check']>> = {},
): HomeCycleSummary['check'] {
  return { verdict, missingCreditsKwh: null, lossConfirmed: false, ...extra }
}

// Fim do ciclo 14/09/2026 + N dias, horário local.
function daysAfterCycleEnd(days: number): Date {
  return new Date(2026, 8, 14 + days, 9, 0)
}

describe('buildHomeTodos — créditos sem explicação no último ciclo', () => {
  const credits = (check: HomeCycleSummary['check']) =>
    buildHomeTodos({ setup: setup(), diagnostics: [], recentCycles: [cycle({ check })] })

  it('LOSS com kWh: cita ciclo e valor com unidade, sem acusar além do veredito', () => {
    const todos = credits(withCheck('LOSS', { missingCreditsKwh: 123.456 }))
    expect(todos).toEqual([
      {
        key: 'utility-credits',
        title: 'Créditos sem explicação no ciclo set/26',
        detail: 'A fatura não mostra 123,46 kWh nem como abatimento nem como saldo. Veja na aba Energia o que conferir.',
        target: 'energy',
      },
    ])
  })

  it('LOSS confirmado usa o rótulo "Créditos faltando" da aba Energia', () => {
    const [todo] = credits(withCheck('LOSS', { missingCreditsKwh: 50, lossConfirmed: true }))
    expect(todo.title).toBe('Créditos faltando no ciclo set/26')
  })

  it.each([[null], [0], [-3]])('LOSS sem valor utilizável (%s): diz sem número, nunca "0 kWh"', (kwh) => {
    const [todo] = credits(withCheck('LOSS', { missingCreditsKwh: kwh }))
    expect(todo.detail).toBe(
      'A fatura não mostra todo kWh registrado nem como abatimento nem como saldo. Veja na aba Energia o que conferir.',
    )
    expect(todo.detail).not.toMatch(/\d/)
  })

  it('IMPOSSIBLE vira tarefa, sem número inventado', () => {
    const [todo] = credits(withCheck('IMPOSSIBLE', { missingCreditsKwh: null }))
    expect(todo).toMatchObject({
      title: 'Registro impossível no ciclo set/26',
      detail:
        'O medidor da distribuidora registrou mais envio à rede do que o inversor mediu. Um dos dois está errado. Veja na aba Energia o que conferir.',
      target: 'energy',
    })
  })

  it.each([['OK'], ['UNVERIFIABLE'], ['SUSPECT']] as const)('%s não vira tarefa', (verdict) => {
    expect(credits(withCheck(verdict, { missingCreditsKwh: 40 }))).toEqual([])
  })

  it('ciclo sem conferência (null) não vira tarefa', () => {
    expect(credits(null)).toEqual([])
  })

  it('vale o ciclo mais recente que tem conferência, mesmo se a lista vier fora de ordem', () => {
    const cycles = [
      cycle({ referenceMonth: '2026-09', check: withCheck('OK') }),
      cycle({ referenceMonth: '2026-08', check: withCheck('LOSS', { missingCreditsKwh: 10 }) }),
    ]
    expect(buildHomeTodos({ setup: setup(), diagnostics: [], recentCycles: cycles })).toEqual([])
    const [todo] = buildHomeTodos({
      setup: setup(),
      diagnostics: [],
      recentCycles: [cycle({ referenceMonth: '2026-09', check: null }), cycles[1]],
    })
    expect(todo.title).toBe('Créditos sem explicação no ciclo ago/26')
  })

  it('histórico ausente ou vazio: nada (nunca adivinha)', () => {
    expect(buildHomeTodos({ setup: setup(), diagnostics: [], recentCycles: null })).toEqual([])
    expect(buildHomeTodos({ setup: setup(), diagnostics: [], recentCycles: [] })).toEqual([])
  })

  it('vem antes de cadastro, faturas pendentes e diagnósticos; o lembrete de fatura vem por último', () => {
    const todos = buildHomeTodos({
      setup: setup({ completed: 5 }),
      diagnostics: [diagnostic('CRITICAL', 'INVERSOR')],
      recentCycles: [cycle({ check: withCheck('LOSS', { missingCreditsKwh: 9 }) })],
      today: daysAfterCycleEnd(60),
    })
    expect(todos.map((todo) => todo.key)).toEqual(['utility-credits', 'setup', 'diagnostic-INVERSOR', 'next-bill'])
  })
})

describe('buildHomeTodos — a próxima fatura já deve ter chegado', () => {
  const reminder = (today: Date, overrides: { setup?: PlantSetup | null; cycles?: HomeCycleSummary[] | null } = {}) =>
    buildHomeTodos({
      setup: overrides.setup === undefined ? setup() : overrides.setup,
      diagnostics: [],
      recentCycles: overrides.cycles === undefined ? [cycle()] : overrides.cycles,
      today,
    })

  it('o limite é de 40 dias, em uma constante', () => {
    expect(BILL_REMINDER_AFTER_DAYS).toBe(40)
  })

  it('40 dias após o fim do ciclo: ainda não', () => {
    expect(reminder(daysAfterCycleEnd(40))).toEqual([])
  })

  it('41 dias: lembra, com o mês do ciclo seguinte ao último confirmado', () => {
    expect(reminder(daysAfterCycleEnd(41))).toEqual([
      {
        key: 'next-bill',
        title: 'A fatura de outubro já deve ter chegado',
        detail: 'Envie o PDF para conferir os créditos.',
        target: 'bills',
      },
    ])
  })

  it('75 dias: ainda fala de uma fatura só', () => {
    expect(reminder(daysAfterCycleEnd(75))[0].title).toBe('A fatura de outubro já deve ter chegado')
  })

  it('76 dias (~2 ciclos): fala em faturas, no plural, a partir do mês seguinte', () => {
    expect(reminder(daysAfterCycleEnd(76))).toEqual([
      {
        key: 'next-bill',
        title: 'Há faturas para enviar desde outubro',
        detail: 'Envie o PDF para conferir os créditos.',
        target: 'bills',
      },
    ])
  })

  it('virada de ano: ciclo de dezembro aponta janeiro', () => {
    const cycles = [cycle({ referenceMonth: '2026-12', cycleEnd: '2026-12-10' })]
    const [todo] = reminder(new Date(2027, 0, 25), { cycles })
    expect(todo.title).toBe('A fatura de janeiro já deve ter chegado')
  })

  it('usa o ciclo mais recente, não o primeiro da lista', () => {
    const cycles = [cycle({ referenceMonth: '2026-09' }), cycle({ referenceMonth: '2026-08', cycleEnd: '2026-08-14' })]
    expect(reminder(daysAfterCycleEnd(41), { cycles })).toHaveLength(1)
    expect(reminder(daysAfterCycleEnd(41), { cycles })[0].title).toMatch(/outubro/)
  })

  it('referência que não bate com a data de fim: frase sem mês', () => {
    const cycles = [cycle({ referenceMonth: '2026-08', cycleEnd: '2026-09-14' })]
    const [todo] = reminder(daysAfterCycleEnd(41), { cycles })
    expect(todo.title).toBe('A próxima fatura já deve ter chegado')
  })

  it('fatura pendente de confirmação suprime o lembrete (a tarefa de conferir já cobre)', () => {
    const todos = reminder(daysAfterCycleEnd(60), { setup: setup({ pendingBills: 1 }) })
    expect(todos.map((todo) => todo.key)).toEqual(['pending-bills'])
  })

  it.each([
    ['sem cadastro lido', { setup: null }],
    ['sem histórico', { cycles: null }],
    ['nenhum ciclo confirmado (o cadastro já pede a 1ª fatura)', { cycles: [] }],
    ['ciclo sem data de fim', { cycles: [cycle({ cycleEnd: null })] }],
  ] as const)('%s: nada', (_name, overrides) => {
    expect(reminder(daysAfterCycleEnd(90), overrides as never)).toEqual([])
  })

  it('sem "hoje" injetado, nunca lembra', () => {
    expect(buildHomeTodos({ setup: setup(), diagnostics: [], recentCycles: [cycle()] })).toEqual([])
  })
})

describe('buildCalmNote (ADR-083)', () => {
  const clean = { missing_days: 0, unavailable_days: 0, provisional_days: 0, incomplete_days: 0 }

  it('ciclo completo: nada a explicar', () => {
    expect(buildCalmNote(clean, 'set/26')).toBeNull()
  })

  it('dia sem leitura: diz que produção e economia podem estar abaixo do real, sem pedir ação', () => {
    expect(buildCalmNote({ ...clean, missing_days: 1 }, 'set/26')).toBe(
      '1 dia do ciclo set/26 ficou sem leitura do inversor, então a produção e a economia desse ciclo podem estar um pouco abaixo do real. Não é algo que você precise resolver.',
    )
  })

  it('dias sem leitura e em consolidação, no plural', () => {
    expect(buildCalmNote({ ...clean, missing_days: 1, unavailable_days: 1, provisional_days: 2 }, 'out/26')).toBe(
      '2 dias do ciclo out/26 ficaram sem leitura do inversor, então a produção e a economia desse ciclo podem estar abaixo do real. 2 dias ainda estão sendo consolidados pelo provedor; os números podem mudar um pouco. Não é algo que você precise resolver.',
    )
  })

  it('nunca afirma que a lacuna não afeta a economia', () => {
    expect(buildCalmNote({ ...clean, missing_days: 2 }, 'set/26')).not.toMatch(/não muda a economia/)
  })
})

describe('buildUnavailableHomeStatus (ADR-083)', () => {
  it('404 (nenhuma produção em 90 dias): aviso explícito, nunca silêncio', () => {
    expect(buildUnavailableHomeStatus('NOT_FOUND')).toMatchObject({
      tone: 'warning',
      title: 'Nenhuma leitura da usina nos últimos 90 dias',
    })
  })

  it('erro de servidor: diz que não conseguiu ler, sem afirmar estado da usina', () => {
    expect(buildUnavailableHomeStatus('SERVER_ERROR')).toMatchObject({
      tone: 'neutral',
      title: 'Não foi possível ler a produção da usina agora',
    })
  })
})

describe('buildWeekWindow (ADR-083)', () => {
  // Contrato real do backend: dia sem leitura NÃO vem na série (sem `null`).
  const withGap = [day('2026-10-14', 20), day('2026-10-16', 22), day('2026-10-19', 25), day('2026-10-22', 24.4)]

  it('7 dias de calendário até a última leitura, com os dias ausentes como null', () => {
    expect(buildWeekWindow(withGap, '2026-10-22')).toEqual([
      { date: '2026-10-16', kwh: 22 },
      { date: '2026-10-17', kwh: null },
      { date: '2026-10-18', kwh: null },
      { date: '2026-10-19', kwh: 25 },
      { date: '2026-10-20', kwh: null },
      { date: '2026-10-21', kwh: null },
      { date: '2026-10-22', kwh: 24.4 },
    ])
  })

  it('não puxa leitura de fora da janela (14/10 fica de fora)', () => {
    expect(buildWeekWindow(withGap, '2026-10-22').map((item) => item.date)).not.toContain('2026-10-14')
  })

  it('atravessa virada de mês', () => {
    expect(buildWeekWindow([day('2026-11-02', 10)], '2026-11-02').map((item) => item.date)).toEqual([
      '2026-10-27',
      '2026-10-28',
      '2026-10-29',
      '2026-10-30',
      '2026-10-31',
      '2026-11-01',
      '2026-11-02',
    ])
  })

  it('sem leitura nenhuma: janela vazia', () => {
    expect(buildWeekWindow([], null)).toEqual([])
  })
})
