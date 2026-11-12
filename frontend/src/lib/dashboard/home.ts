// Regras da aba Início (ADR-083): uma frase de situação e a lista "Precisa de
// você". Puro e sem React, para ser testado isoladamente.
//
// Princípio: alerta só quando o dono precisa AGIR. Um dia sem leitura num
// ciclo já fechado, a perda normal por calor ou um baseline que ainda está em
// formação não são tarefas — são explicados uma vez, em linguagem simples, e
// nunca viram "Atenção" na tela principal.

import type { AnomalyDailyPoint, Diagnostic } from './contracts'
import type { PlantSetup } from './plant-setup-contracts'
import type { UtilityCheckVerdict } from './monthly-history-contracts'
import { productionAlertSignal } from './production-alerts'
import { formatCycleLabel, formatNumber, formatShortDate, toNumber } from '../format'

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

export type HomeTodoTarget = 'setup' | 'bills' | 'diagnostics' | 'energy'

export interface HomeTodo {
  key: string
  title: string
  detail: string
  target: HomeTodoTarget
}

// Dias após o FIM do último ciclo confirmado a partir dos quais a próxima
// fatura "já deve ter chegado". Decisão do dono (12/11/2026): 40 dias cobre o
// ciclo de ~30 dias mais a emissão e a entrega da distribuidora.
export const BILL_REMINDER_AFTER_DAYS = 40

// Resumo mínimo de um ciclo fechado do histórico mensal (`/reports/monthly/history`),
// só com o que o Início usa. `check` é `null` quando o servidor não conferiu o
// ciclo — nunca vira "OK".
export interface HomeCycleSummary {
  referenceMonth: string
  cycleEnd: string | null
  check: {
    verdict: UtilityCheckVerdict
    missingCreditsKwh: number | null
    lossConfirmed: boolean
  } | null
}

const MONTH_NAMES = [
  'janeiro',
  'fevereiro',
  'março',
  'abril',
  'maio',
  'junho',
  'julho',
  'agosto',
  'setembro',
  'outubro',
  'novembro',
  'dezembro',
]

// Mais recente primeiro; `referenceMonth` ("AAAA-MM") ordena como texto.
function newestFirst(cycles: readonly HomeCycleSummary[]): HomeCycleSummary[] {
  return [...cycles].sort((a, b) => b.referenceMonth.localeCompare(a.referenceMonth))
}

// Créditos que o servidor não viu na fatura. Só LOSS e IMPOSSIBLE pedem ação
// do dono (a aba Energia manda conferir com a distribuidora / pedir aferição).
// SUSPECT ("fora do padrão... pode ser o medidor ou mais consumo") é só um
// aviso explicado lá; OK e UNVERIFIABLE não têm o que fazer.
function buildCreditsTodo(cycles: readonly HomeCycleSummary[]): HomeTodo | null {
  const latest = newestFirst(cycles).find((cycle) => cycle.check != null)
  const check = latest?.check
  if (!latest || !check) return null
  const label = formatCycleLabel(latest.referenceMonth)

  if (check.verdict === 'LOSS') {
    // Sem número (ausente ou não positivo), diz sem número: nunca "0 kWh".
    const amount =
      check.missingCreditsKwh != null && check.missingCreditsKwh > 0
        ? `${formatNumber(check.missingCreditsKwh, 2)} kWh`
        : null
    const shown = amount
      ? `A fatura não mostra ${amount} nem como abatimento nem como saldo.`
      : 'A fatura não mostra todo kWh registrado nem como abatimento nem como saldo.'
    return {
      key: 'utility-credits',
      title: check.lossConfirmed ? `Créditos faltando no ciclo ${label}` : `Créditos sem explicação no ciclo ${label}`,
      detail: `${shown} Veja na aba Energia o que conferir.`,
      target: 'energy',
    }
  }
  if (check.verdict === 'IMPOSSIBLE') {
    return {
      key: 'utility-credits',
      title: `Registro impossível no ciclo ${label}`,
      detail:
        'A distribuidora registrou mais energia enviada à rede do que o inversor produziu. Veja na aba Energia o que conferir.',
      target: 'energy',
    }
  }
  return null
}

// "A fatura de <mês> já deve ter chegado": o mês é o do ciclo seguinte ao
// último confirmado (referência + 1). Só afirma o mês se a referência
// concordar com a data de fim do ciclo; senão a frase fica sem mês.
function buildBillReminder(
  cycles: readonly HomeCycleSummary[],
  today: Date,
): HomeTodo | null {
  const latest = newestFirst(cycles)[0]
  if (!latest?.cycleEnd) return null
  if (daysBetween(latest.cycleEnd, today) <= BILL_REMINDER_AFTER_DAYS) return null

  const match = /^(\d{4})-(\d{2})$/.exec(latest.referenceMonth)
  const monthIndex = match ? Number(match[2]) - 1 : -1
  const consistent = monthIndex >= 0 && monthIndex < 12 && latest.cycleEnd.slice(0, 7) === latest.referenceMonth
  const next = consistent ? MONTH_NAMES[(monthIndex + 1) % 12] : null

  return {
    key: 'next-bill',
    title: next ? `A fatura de ${next} já deve ter chegado` : 'A próxima fatura já deve ter chegado',
    detail: 'Envie o PDF para conferir os créditos.',
    target: 'bills',
  }
}

// O que precisa do dono, em ordem de importância. Só entra o que tem ação
// concreta para ele fazer; o resto fica explicado onde o dado aparece.
//
// Ordem: créditos não explicados (o achado mais valioso, vai primeiro) →
// cadastro → faturas pendentes → diagnósticos críticos → lembrete da próxima
// fatura (rotina, por último). `recentCycles`/`today` são opcionais: sem
// histórico (ausente, falho ou vazio) nenhuma das duas tarefas novas aparece.
export function buildHomeTodos({
  setup,
  diagnostics,
  recentCycles = null,
  today = null,
}: {
  setup: PlantSetup | null
  diagnostics: readonly Diagnostic[]
  recentCycles?: readonly HomeCycleSummary[] | null
  today?: Date | null
}): HomeTodo[] {
  const todos: HomeTodo[] = []

  const credits = recentCycles ? buildCreditsTodo(recentCycles) : null
  if (credits) todos.push(credits)

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

  // Precisa do cadastro lido (sem fatura pendente) e de ao menos um ciclo
  // confirmado: sem nenhum, o item "Primeira fatura confirmada" do cadastro
  // já pede a primeira fatura.
  if (recentCycles && recentCycles.length > 0 && today && setup && setup.pendingBills === 0) {
    const reminder = buildBillReminder(recentCycles, today)
    if (reminder) todos.push(reminder)
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
