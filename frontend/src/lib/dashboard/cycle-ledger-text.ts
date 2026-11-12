// Texto do "conta ciclo a ciclo" (aba Dinheiro), em funções puras. Frases
// alinhadas às que o app já usa em `SavingsGapsPanel`/`FinancialSection`/
// `HomeSavingsCard` ("Estimado", "pode estar subestimada", "fórmula antiga").
// Nenhuma conta com dinheiro: só formatação do que o backend já entregou.

import { formatCurrency, formatCycleLabel } from '../format'
import { LEDGER_API_WITHOUT_SAVINGS, type LedgerCycle, type SavingsWindow } from './cycle-ledger-contracts'

export const LEDGER_SEAL_ESTIMATED = 'Estimada'

// Motivo tipado do backend, em palavras (nunca "R$ 0,00").
export function ledgerReasonText(reason: string | null): string {
  switch (reason) {
    case 'NO_PRODUCTION_DATA':
      return 'Economia indisponível: sem produção do inversor registrada no período.'
    case 'TARIFF_NOT_AVAILABLE':
      return 'Economia indisponível: a fatura não trouxe a tarifa.'
    case 'NO_CONSUMPTION_DATA':
      return 'Economia indisponível: sem dado de consumo no período.'
    case 'REPORT_PREDATES_SAVINGS':
      return 'Economia indisponível: relatório anterior ao cálculo de economia.'
    case LEDGER_API_WITHOUT_SAVINGS:
      return 'Economia por ciclo ainda não informada por esta versão do servidor.'
    default:
      return 'Economia indisponível para este ciclo.'
  }
}

// Selos além de "Estimada", só quando há economia. Texto, não só cor.
export function ledgerExtraSeals(cycle: LedgerCycle): string[] {
  if (cycle.estimatedSavingsBrl === null) return []
  const seals: string[] = []
  if (cycle.savingsTariffSource === 'BILL_TARIFF') {
    seals.push('Tarifa da própria fatura: pode estar subestimada')
  }
  if (cycle.savingsGapCause === 'PARTIAL_PRODUCTION') {
    seals.push('Ciclo parcial, com dias sem leitura do inversor: pode estar subestimada')
  }
  if (cycle.savingsGapCause === 'OUTDATED_CALCULATION') {
    seals.push('Calculada pela fórmula antiga: pode estar subestimada')
  }
  return seals
}

// Comparação, não conta: só diz se o texto decimal é negativo.
export function isNegativeMoney(value: string | null): boolean {
  return value !== null && Number(value) < 0
}

export const LEDGER_NEGATIVE_NOTE =
  'Pela estimativa, a fatura saiu mais alta do que sairia sem a usina.'

// Por que a linha não entra na soma (ordem: refaturamento, ligação, antes da ligação).
export function ledgerExclusionText(cycle: LedgerCycle): string | null {
  if (cycle.supersededByRebilling) {
    return 'Não entra na soma: mês refaturado, vale só o cálculo mais recente deste mês.'
  }
  if (cycle.isCommissioningMonth === true) {
    return 'Não entra na soma: mês da ligação da usina (ciclo parcial).'
  }
  if (cycle.isBeforeCommissioning === true) {
    return 'Não entra na soma: mês anterior à ligação da usina.'
  }
  return null
}

// "dd/mm/aaaa" no fuso de Brasília; `null` se a data não for legível.
export function formatCalculatedOn(isoDateTime: string | null): string | null {
  if (isoDateTime === null) return null
  const date = new Date(isoDateTime)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' })
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

function period(window: SavingsWindow): string {
  if (!window.firstReferenceMonth || !window.lastReferenceMonth) return ''
  const first = formatCycleLabel(window.firstReferenceMonth)
  const last = formatCycleLabel(window.lastReferenceMonth)
  return first === last ? ` (${first})` : ` (${first} a ${last})`
}

// Linha do total: só números do `savings_window`.
export function ledgerTotalLine(window: SavingsWindow): string {
  if (window.totalEstimatedSavingsBrl === null) {
    return 'Nenhum ciclo do período tem economia calculada, por isso não há soma.'
  }
  const cycles = window.cyclesInWindow === 1 ? 'ciclo' : 'ciclos'
  return `Economia estimada somada: ${formatCurrency(window.totalEstimatedSavingsBrl)}, em ${window.cyclesWithSavings} de ${window.cyclesInWindow} ${cycles}${period(window)}`
}

// O que ficou fora da soma, quando algum contador é maior que zero.
export function ledgerLeftOutNote(window: SavingsWindow): string | null {
  const parts: string[] = []
  if (window.cyclesExcludedCommissioning > 0) {
    parts.push(
      `${plural(window.cyclesExcludedCommissioning, 'ciclo do mês da ligação da usina ou anterior', 'ciclos do mês da ligação da usina ou anteriores')}`,
    )
  }
  if (window.cyclesSupersededByRebilling > 0) {
    parts.push(
      `${plural(window.cyclesSupersededByRebilling, 'cálculo de mês refaturado (cada mês conta uma vez só)', 'cálculos de meses refaturados (cada mês conta uma vez só)')}`,
    )
  }
  if (window.cyclesWithoutSavings > 0) {
    parts.push(plural(window.cyclesWithoutSavings, 'ciclo sem economia calculada', 'ciclos sem economia calculada'))
  }
  return parts.length === 0 ? null : `Ficaram fora da soma: ${parts.join('; ')}.`
}

// Ciclos dentro da soma que podem estar subestimados.
export function ledgerQualityNote(window: SavingsWindow): string | null {
  const parts: string[] = []
  if (window.cyclesWithBillTariff > 0) {
    parts.push(`${plural(window.cyclesWithBillTariff, 'ciclo usa', 'ciclos usam')} a tarifa da própria fatura`)
  }
  if (window.cyclesWithOutdatedOrPartial > 0) {
    parts.push(
      `${plural(window.cyclesWithOutdatedOrPartial, 'ciclo foi calculado', 'ciclos foram calculados')} pela fórmula antiga ou com dias sem leitura do inversor`,
    )
  }
  return parts.length === 0 ? null : `Dentro da soma, ${parts.join(' e ')}: o total pode estar subestimado.`
}

export const LEDGER_COMMISSIONING_UNKNOWN_NOTE =
  'A usina não tem data de ligação cadastrada, então a soma pode incluir um mês parcial. Informe a data em'

export const LEDGER_BILL_NOTE =
  'O valor da fatura inclui iluminação pública e outros itens, não só a energia.'

export const LEDGER_SNAPSHOT_NOTE =
  'Cada economia vem do relatório gravado do ciclo, na data de “calculado em”; pode diferir do cálculo ao vivo do ciclo mais recente, mais acima.'
