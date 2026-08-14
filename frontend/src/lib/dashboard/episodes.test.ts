import { describe, expect, it } from 'vitest'
import { buildAnomalyEpisodes } from './episodes'
import type { AnomalyDailyPoint, AnomalyDiagnostic, AnomalyLevel } from './contracts'

function diagnostic(
  code: string,
  level: AnomalyLevel,
  overrides: Partial<AnomalyDiagnostic> = {}
): AnomalyDiagnostic {
  return {
    code,
    level,
    message: `mensagem de ${code}`,
    recommended_action: `ação de ${code}`,
    ...overrides,
  }
}

function day(date: string, diagnostics: AnomalyDiagnostic[]): AnomalyDailyPoint {
  return {
    date,
    actual_production_kwh: 40,
    expected_production_kwh: 50,
    level: diagnostics[0]?.level ?? 'NORMAL',
    deviation_percent: -20,
    irradiation_kwh_m2: null,
    yield_kwh_per_kwh_m2: null,
    yield_deviation_from_period_percent: null,
    temperature_mean_c: null,
    diagnostics,
  }
}

const LOW = 'LOW_PRODUCTION_VS_EXPECTED'
const OTHER = 'UNEXPLAINED_LOW_PRODUCTION'

describe('buildAnomalyEpisodes', () => {
  it('agrupa dias de calendário consecutivos com o mesmo código num único episódio', () => {
    const episodes = buildAnomalyEpisodes([
      day('2026-08-01', [diagnostic(LOW, 'ANOMALY')]),
      day('2026-08-02', [diagnostic(LOW, 'ANOMALY')]),
      day('2026-08-03', [diagnostic(LOW, 'ANOMALY')]),
    ])

    expect(episodes).toHaveLength(1)
    expect(episodes[0].startDate).toBe('2026-08-01')
    expect(episodes[0].endDate).toBe('2026-08-03')
    expect(episodes[0].durationDays).toBe(3)
  })

  // Um buraco de coleta não pode virar um episódio contínuo: o backend só emite
  // dias com produção registrada, então o array pode pular datas.
  it('separa episódios quando há lacuna de calendário, mesmo com o mesmo código', () => {
    const episodes = buildAnomalyEpisodes([
      day('2026-08-01', [diagnostic(LOW, 'ANOMALY')]),
      day('2026-08-05', [diagnostic(LOW, 'ANOMALY')]),
    ])

    expect(episodes).toHaveLength(2)
    expect(episodes[0].durationDays).toBe(1)
    expect(episodes[1].startDate).toBe('2026-08-05')
  })

  it('separa episódios quando um dia normal fica no meio', () => {
    const episodes = buildAnomalyEpisodes([
      day('2026-08-01', [diagnostic(LOW, 'ANOMALY')]),
      day('2026-08-02', [diagnostic('PERFORMANCE_WITHIN_EXPECTED_RANGE', 'NORMAL')]),
      day('2026-08-03', [diagnostic(LOW, 'ANOMALY')]),
    ])

    expect(episodes).toHaveLength(2)
    expect(episodes.map((item) => item.startDate)).toEqual(['2026-08-01', '2026-08-03'])
  })

  it('separa episódios quando o código muda em dias consecutivos', () => {
    const episodes = buildAnomalyEpisodes([
      day('2026-08-01', [diagnostic(LOW, 'ANOMALY')]),
      day('2026-08-02', [diagnostic(OTHER, 'ATTENTION')]),
    ])

    expect(episodes).toHaveLength(2)
    expect(episodes.map((item) => item.code)).toEqual([LOW, OTHER])
  })

  // Regra de honestidade do ADR-075: culpar a usina por lacuna do nosso próprio
  // dado seria desonesto.
  it.each(['PERFORMANCE_WITHIN_EXPECTED_RANGE', 'INCOMPLETE_INPUT_DATA', 'EXPECTED_PRODUCTION_UNAVAILABLE'])(
    'nunca cria episódio para o código excluído %s',
    (code) => {
      const episodes = buildAnomalyEpisodes([
        day('2026-08-01', [diagnostic(code, 'ATTENTION')]),
        day('2026-08-02', [diagnostic(code, 'ATTENTION')]),
      ])

      expect(episodes).toEqual([])
    }
  )

  // Severidade do episódio vem do pior dia, não do primeiro nem de uma média —
  // um episódio que escalou para CRITICAL não pode ser exibido como ATTENTION.
  it('usa o nível, a mensagem e a ação do dia mais severo do episódio', () => {
    const episodes = buildAnomalyEpisodes([
      day('2026-08-01', [diagnostic(LOW, 'ATTENTION', { message: 'leve', recommended_action: 'observar' })]),
      day('2026-08-02', [diagnostic(LOW, 'CRITICAL', { message: 'grave', recommended_action: 'agir hoje' })]),
      day('2026-08-03', [diagnostic(LOW, 'ATTENTION', { message: 'leve de novo', recommended_action: 'observar' })]),
    ])

    expect(episodes).toHaveLength(1)
    expect(episodes[0].level).toBe('CRITICAL')
    expect(episodes[0].message).toBe('grave')
    expect(episodes[0].recommendedAction).toBe('agir hoje')
  })

  // `ongoing` é medido contra a última data da série recebida, nunca contra a
  // data de hoje — a UI não pode afirmar que algo segue acontecendo quando o
  // dado mais recente é de semanas atrás.
  it('marca como em curso apenas o episódio que alcança o último dia da série', () => {
    const episodes = buildAnomalyEpisodes([
      day('2026-08-01', [diagnostic(LOW, 'ANOMALY')]),
      day('2026-08-02', [diagnostic('PERFORMANCE_WITHIN_EXPECTED_RANGE', 'NORMAL')]),
      day('2026-08-03', [diagnostic(OTHER, 'ATTENTION')]),
    ])

    expect(episodes).toHaveLength(2)
    expect(episodes[0].ongoing).toBe(false)
    expect(episodes[1].ongoing).toBe(true)
  })

  it('devolve lista vazia para série vazia ou sem diagnósticos', () => {
    expect(buildAnomalyEpisodes([])).toEqual([])
    expect(buildAnomalyEpisodes([day('2026-08-01', [])])).toEqual([])
  })

  // O motor hoje devolve no máximo um diagnóstico por dia, mas o agrupamento
  // não deve depender dessa garantia implícita do backend.
  it('usa o primeiro diagnóstico elegível quando o dia traz um excluído antes', () => {
    const episodes = buildAnomalyEpisodes([
      day('2026-08-01', [diagnostic('INCOMPLETE_INPUT_DATA', 'ATTENTION'), diagnostic(LOW, 'ANOMALY')]),
    ])

    expect(episodes).toHaveLength(1)
    expect(episodes[0].code).toBe(LOW)
  })
})
