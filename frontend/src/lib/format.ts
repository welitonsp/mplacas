import type { MetricValue } from './dashboard/contracts'

export function formatNumber(value: MetricValue, maximumFractionDigits = 2): string {
  if (value == null) return '—'
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  return numeric.toLocaleString('pt-BR', { maximumFractionDigits })
}

export function formatCurrency(value: MetricValue): string {
  if (value == null) return '—'
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
