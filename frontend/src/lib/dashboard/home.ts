// Regras da aba Início (ADR-083): uma frase de situação e a lista "Precisa de
// você". Puro e sem React, para ser testado isoladamente.
//
// Princípio: alerta só quando o dono precisa AGIR. Um dia sem leitura num
// ciclo já fechado, a perda normal por calor ou um baseline que ainda está em
// formação não são tarefas — são explicados uma vez, em linguagem simples, e
// nunca viram "Atenção" na tela principal.

import type { AnomalyDailyPoint, Diagnostic } from './contracts'
import type { PlantSetup } from './plant-setup-contracts'
import { productionAlertSignal } from './production-alerts'
import { formatNumber, formatShortDate, toNumber } from '../format'

export type HomeTone = 'success' | 'warning' | 'danger' | 'neutral'

export interface HomeStatus {
  tone: HomeTone
  title: string
  detail: string
}

// Sem leitura há 3 dias ou mais: a coleta diária roda de madrugada sobre o dia
// anterior, então "ontem" é o normal e "anteontem" ainda pode ser atraso de
// sincronização do provedor. A partir de 3 dias é falta de comunicação real.
export const STALE_TELEMETRY_DAYS = 3

function daysBetween(fromIso: string, to: Date): number {
  const [year, month, day] = fromIso.split('-').map(Number)
  const from = Date.UTC(year, month - 1, day)
  const target = Date.UTC(to.getFullYear(), to.getMonth(), to.getDate())
  return Math.round((target - from) / 86_400_000)
}

export function buildHomeStatus({
  daily,
  latestDataDate,
  today,
}: {
  daily: readonly AnomalyDailyPoint[]
  latestDataDate: string | null
  today: Date
}): HomeStatus {
  if (latestDataDate == null) {
    return {
      tone: 'neutral',
      title: 'Aguardando a primeira leitura da usina',
      detail: 'Assim que o inversor enviar o primeiro dia de produção, a situação aparece aqui.',
    }
  }

  const latestPoint = daily.find((point) => point.date === latestDataDate)
  const latestKwh = toNumber(latestPoint?.actual_production_kwh ?? null)
  const latestText =
    latestKwh == null
      ? `Último dado: ${formatShortDate(latestDataDate)}`
      : `Último dia: ${formatNumber(latestKwh, 1)} kWh · dado de ${formatShortDate(latestDataDate)}`

  const staleDays = daysBetween(latestDataDate, today)
  if (staleDays >= STALE_TELEMETRY_DAYS) {
    return {
      tone: 'warning',
      title: `Sem leitura da usina desde ${formatShortDate(latestDataDate)}`,
      detail:
        'A usina pode estar gerando normalmente: o mais comum é falta de internet no equipamento. Confira a conexão dele.',
    }
  }

  const signal = productionAlertSignal(daily)
  if (signal.tone === 'danger') {
    return {
      tone: 'danger',
      title: 'Produção bem abaixo do normal',
      detail: `${signal.detail} Se o tempo esteve bom, vale verificar a usina.`,
    }
  }
  if (signal.tone === 'warning') {
    return {
      tone: 'warning',
      title: 'Produção um pouco abaixo do normal',
      detail: `${signal.detail} Pode ser só tempo nublado; acompanhe nos próximos dias.`,
    }
  }
  if (signal.tone === 'success') {
    return { tone: 'success', title: 'Sua usina está funcionando bem', detail: latestText }
  }
  return { tone: 'neutral', title: 'Sua usina está gerando', detail: latestText }
}

// Histórico diário indisponível: nunca some em silêncio. 404 do backend =
// nenhuma produção nos últimos 90 dias (usina nova OU telemetria parada há
// muito tempo — as duas pedem o mesmo cuidado do dono).
export function buildUnavailableHomeStatus(error: 'NOT_FOUND' | 'SERVER_ERROR'): HomeStatus {
  if (error === 'NOT_FOUND') {
    return {
      tone: 'warning',
      title: 'Nenhuma leitura da usina nos últimos 90 dias',
      detail:
        'Se a usina já está ligada, confira a internet do equipamento e a conexão com o provedor do inversor.',
    }
  }
  return {
    tone: 'neutral',
    title: 'Não foi possível ler a produção da usina agora',
    detail: 'Use Atualizar para tentar de novo em instantes.',
  }
}

export interface WeekDay {
  date: string
  kwh: number | null
}

function shiftIsoDate(iso: string, deltaDays: number): string {
  const [year, month, day] = iso.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day + deltaDays))
  return date.toISOString().slice(0, 10)
}

// Os 7 dias de CALENDÁRIO que terminam no último dia com leitura. O backend
// omite da série os dias sem leitura (não devolve `null`), então pegar as 7
// últimas entradas podia cobrir 10 dias e somar como se fossem 7. Aqui cada
// dia do calendário tem seu lugar; o que não veio fica `null` ("sem dado").
export function buildWeekWindow(
  daily: readonly AnomalyDailyPoint[],
  latestDataDate: string | null,
  days = 7,
): WeekDay[] {
  if (latestDataDate == null) return []
  const byDate = new Map(daily.map((point) => [point.date, toNumber(point.actual_production_kwh)]))
  return Array.from({ length: days }, (_, index) => {
    const date = shiftIsoDate(latestDataDate, index - (days - 1))
    return { date, kwh: byDate.get(date) ?? null }
  })
}

// Diagnósticos de lacuna de telemetria não viram tarefa: o dono não tem o que
// fazer num ciclo fechado ("executar backfill" é tarefa de operação), e a
// lacuna já é explicada uma vez em `buildCalmNote`. Telemetria parada AGORA é
// tratada pela frase de situação (`buildHomeStatus`).
const DATA_GAP_DIAGNOSTIC_CODES: ReadonlySet<string> = new Set(['MISSING_DAILY_DATA'])

export type HomeTodoTarget = 'setup' | 'bills' | 'diagnostics'

export interface HomeTodo {
  key: string
  title: string
  detail: string
  target: HomeTodoTarget
}

// O que precisa do dono, em ordem de importância. Só entra o que tem ação
// concreta para ele fazer; o resto fica explicado onde o dado aparece.
export function buildHomeTodos({
  setup,
  diagnostics,
}: {
  setup: PlantSetup | null
  diagnostics: readonly Diagnostic[]
}): HomeTodo[] {
  const todos: HomeTodo[] = []

  if (setup && setup.completed < setup.total) {
    const missing = setup.total - setup.completed
    todos.push({
      key: 'setup',
      title: 'Completar o cadastro da usina',
      detail:
        missing === 1
          ? `Falta 1 item (${setup.completed} de ${setup.total}). Cada item libera uma parte do sistema.`
          : `Faltam ${missing} itens (${setup.completed} de ${setup.total}). Cada item libera uma parte do sistema.`,
      target: 'setup',
    })
  }

  if (setup && setup.pendingBills > 0) {
    todos.push({
      key: 'pending-bills',
      title:
        setup.pendingBills === 1
          ? 'Conferir 1 fatura importada'
          : `Conferir ${setup.pendingBills} faturas importadas`,
      detail: 'Confira os valores lidos e confirme. É da fatura que sai a economia real.',
      target: 'bills',
    })
  }

  // Só o que o motor classificou como crítico. Avisos (WARNING) e informativos
  // continuam na lista completa do ciclo, sem virar tarefa.
  for (const diagnostic of diagnostics) {
    if (diagnostic.severity !== 'CRITICAL') continue
    if (DATA_GAP_DIAGNOSTIC_CODES.has(diagnostic.code)) continue
    todos.push({
      key: `diagnostic-${diagnostic.code}`,
      title: diagnostic.message,
      detail: diagnostic.recommended_action,
      // A lista completa de diagnósticos mora no próprio Início (recolhida).
      target: 'diagnostics',
    })
  }

  return todos
}

// Explica, uma vez e sem alarme, o que não pede ação do dono — mas sem
// esconder o efeito: a economia do ciclo usa a produção do inversor
// (autoconsumo = produção − injetado, `energy_engine.py`), então um dia sem
// leitura deixa produção e economia ABAIXO do real. Dias em consolidação podem
// mudar os números do ciclo.
export function buildCalmNote(
  quality: { missing_days: number; unavailable_days: number; provisional_days: number; incomplete_days: number },
  cycleLabel: string,
): string | null {
  const gaps = quality.missing_days + quality.unavailable_days
  const pending = quality.provisional_days + quality.incomplete_days
  const parts: string[] = []
  if (gaps > 0) {
    parts.push(
      gaps === 1
        ? `1 dia do ciclo ${cycleLabel} ficou sem leitura do inversor, então a produção e a economia desse ciclo podem estar um pouco abaixo do real.`
        : `${gaps} dias do ciclo ${cycleLabel} ficaram sem leitura do inversor, então a produção e a economia desse ciclo podem estar abaixo do real.`,
    )
  }
  if (pending > 0) {
    parts.push(
      pending === 1
        ? '1 dia ainda está sendo consolidado pelo provedor; os números podem mudar um pouco.'
        : `${pending} dias ainda estão sendo consolidados pelo provedor; os números podem mudar um pouco.`,
    )
  }
  if (parts.length === 0) return null
  return `${parts.join(' ')} Não é algo que você precise resolver.`
}
