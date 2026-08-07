import type { MetricValue } from './dashboard/contracts'

export function formatNumber(value: MetricValue, maximumFractionDigits = 2): string {
  if (value == null) return '—'
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  return numeric.toLocaleString('pt-BR', { maximumFractionDigits })
}

export function formatCurrency(value: MetricValue): string {
  if (value == null) return 'R$ —'
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  return numeric.toLocaleString('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    maximumFractionDigits: 2,
  })
}

export function toNumber(value: MetricValue): number | null {
  if (value == null) return null
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

export function clampPercent(value: number): number {
  return Math.min(Math.max(value, 0), 100)
}

export function formatShortDate(isoDate: string): string {
  const [, month, day] = isoDate.split('-')
  if (!month || !day) return isoDate
  return `${day}/${month}`
}

export function formatFullDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-')
  if (!year || !month || !day) return isoDate
  return `${day}/${month}/${year}`
}

const CYCLE_MONTH_ABBREVIATIONS = [
  'jan',
  'fev',
  'mar',
  'abr',
  'mai',
  'jun',
  'jul',
  'ago',
  'set',
  'out',
  'nov',
  'dez',
]

// Converte `"2026-07"` (o `reference_month` de um ciclo de faturamento) em
// `"jul/26"` para o rótulo compacto do gráfico de histórico. Um valor que não
// case o formato `AAAA-MM` (ex.: um formato futuro do backend que este
// frontend ainda não conhece) devolve a string crua em vez de quebrar — mesmo
// princípio defensivo do resto dos parsers do dashboard.
export function formatCycleLabel(referenceMonth: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(referenceMonth)
  if (!match) return referenceMonth
  const [, year, month] = match
  const monthIndex = Number(month) - 1
  const abbreviation = CYCLE_MONTH_ABBREVIATIONS[monthIndex]
  if (!abbreviation) return referenceMonth
  return `${abbreviation}/${year.slice(2)}`
}
