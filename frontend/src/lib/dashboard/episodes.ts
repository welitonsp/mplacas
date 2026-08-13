// Linha do tempo de episódios (ADR-075, Decisão 4.2) — agrega os
// diagnósticos por dia que `parseAnomalyDaily` já traz do backend
// (`AnomalyDailyPoint.diagnostics`) em sequências de dias consecutivos com o
// mesmo `code`. Puro agrupamento e formatação de itens já classificados pelo
// motor determinístico (`intelligence/anomaly_engine.py`): nenhum limiar,
// nenhuma divisão, nenhuma multiplicação de grandeza física, nenhuma
// comparação contra constante de severidade é introduzida aqui — ver
// `no-client-computed-anomaly-episodes.test.ts` para a guarda estática.
import type { AnomalyDailyPoint, AnomalyLevel } from './contracts'
import { LEVEL_RANK } from './visuals'

// Códigos que descrevem uma lacuna do NOSSO dado ou baseline, não um
// problema da usina (ADR-075, Decisão 5.2) — nunca entram na linha do
// tempo: culpar a usina por um buraco de coleta ou por baseline ainda não
// disponível seria desonesto. `PERFORMANCE_WITHIN_EXPECTED_RANGE`
// (normalidade, Decisão 5.1) também fica fora — um dia normal nunca vira
// episódio, e sua presença aqui quebraria o agrupamento de dias vizinhos com
// o mesmo código de anomalia (o comportamento certo: um dia normal separa
// dois episódios, nunca os funde).
const EXCLUDED_DIAGNOSTIC_CODES: ReadonlySet<string> = new Set([
  'PERFORMANCE_WITHIN_EXPECTED_RANGE',
  'INCOMPLETE_INPUT_DATA',
  'EXPECTED_PRODUCTION_UNAVAILABLE',
])

export interface AnomalyEpisode {
  code: string
  level: AnomalyLevel
  startDate: string
  endDate: string
  durationDays: number
  // `true` quando o episódio inclui o último dia da série (`daily`) recebida
  // — nunca calculado contra a data de hoje, só contra o que o backend
  // devolveu (ADR-075, Decisão 4.2: "rotulado 'em curso', nunca com data de
  // fim futura").
  ongoing: boolean
  message: string
  recommendedAction: string
}

interface IncludedDay {
  date: string
  code: string
  level: AnomalyLevel
  message: string
  recommendedAction: string
}

// Um dia entra na linha do tempo só se tiver um diagnóstico com código fora
// da lista de exclusão acima. Hoje o motor nunca devolve mais de um
// diagnóstico por dia (ver comentário de `AnomalyDailyPoint.diagnostics`),
// mas o primeiro elegível é usado de propósito, para não depender dessa
// garantia implícita do backend.
function includedDay(day: AnomalyDailyPoint): IncludedDay | null {
  const diagnostic = day.diagnostics.find((item) => !EXCLUDED_DIAGNOSTIC_CODES.has(item.code))
  if (diagnostic === undefined) return null
  return {
    date: day.date,
    code: diagnostic.code,
    level: diagnostic.level,
    message: diagnostic.message,
    recommendedAction: diagnostic.recommended_action,
  }
}

// Compara datas em calendário, não posições adjacentes no array `daily` —
// que pode ter lacunas quando um dia inteiro não tem nenhuma linha de
// produção coletada (`intelligence/anomaly_service.py::
// analyze_recent_persisted_anomalies` só emite dias com `DailyEnergy`
// registrado; `for current_day in sorted(energy_by_day)`). Um buraco de
// coleta entre dois dias do mesmo código não deve ser apresentado como um
// único episódio contínuo. `Date.parse` com `T00:00:00Z` fixa UTC, evitando
// qualquer sensibilidade a fuso horário do navegador.
function isNextCalendarDay(previousIsoDate: string, currentIsoDate: string): boolean {
  const previous = Date.parse(`${previousIsoDate}T00:00:00Z`)
  const current = Date.parse(`${currentIsoDate}T00:00:00Z`)
  return current - previous === 24 * 60 * 60 * 1000
}

// Agrupa `daily` (ordem cronológica ascendente, garantida pelo backend) em
// episódios. Dentro de um episódio, `level`/`message`/`recommendedAction`
// vêm do dia mais severo (`LEVEL_RANK`, única declaração do projeto — ver
// `visuals.ts`), nunca de uma média ou do primeiro/último dia.
export function buildAnomalyEpisodes(daily: readonly AnomalyDailyPoint[]): AnomalyEpisode[] {
  const lastSeriesDate = daily.length > 0 ? daily[daily.length - 1].date : null
  const episodes: AnomalyEpisode[] = []
  let current: IncludedDay[] = []

  function flushCurrentEpisode(): void {
    if (current.length === 0) return
    const worst = current.reduce((worstSoFar, item) =>
      LEVEL_RANK[item.level] < LEVEL_RANK[worstSoFar.level] ? item : worstSoFar
    )
    const first = current[0]
    const last = current[current.length - 1]
    episodes.push({
      code: first.code,
      level: worst.level,
      startDate: first.date,
      endDate: last.date,
      durationDays: current.length,
      ongoing: last.date === lastSeriesDate,
      message: worst.message,
      recommendedAction: worst.recommendedAction,
    })
    current = []
  }

  for (const day of daily) {
    const included = includedDay(day)
    if (included === null) {
      flushCurrentEpisode()
      continue
    }

    const previous = current[current.length - 1] as IncludedDay | undefined
    const continuesEpisode =
      previous !== undefined &&
      previous.code === included.code &&
      isNextCalendarDay(previous.date, included.date)

    if (previous !== undefined && !continuesEpisode) {
      flushCurrentEpisode()
    }
    current.push(included)
  }
  flushCurrentEpisode()

  return episodes
}
