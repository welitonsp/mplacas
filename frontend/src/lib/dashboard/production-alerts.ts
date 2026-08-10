import type { AnomalyDailyPoint, Severity } from './contracts'
import { formatNumber, toNumber } from '../format'

export type ProductionPeriodDays = 7 | 30 | 90
export type ProductionSignalTone = Severity

export const PRODUCTION_PERIOD_OPTIONS: ReadonlyArray<ProductionPeriodDays> = [7, 30, 90]
export const DEFAULT_PRODUCTION_PERIOD_DAYS: ProductionPeriodDays = 7

export const EXPECTED_WARNING_THRESHOLD_PERCENT = 85
export const EXPECTED_CRITICAL_THRESHOLD_PERCENT = 75
export const HISTORICAL_WARNING_DROP_PERCENT = -15
export const HISTORICAL_CRITICAL_DROP_PERCENT = -25

export interface ProductionAverage {
  average: number | null
  days: number
}

export interface ProductionPerformance {
  percent: number | null
  assessedDays: number
}

export interface ProductionAlertSignal {
  tone: ProductionSignalTone
  label: string
  detail: string
}

export interface ProductionAverageTrend {
  percent: number | null
  tone: ProductionSignalTone
  label: string
  detail: string
  recentAverage: number | null
  previousAverage: number | null
  recentDays: number
  previousDays: number
}

export function latestProductionDays<T>(items: readonly T[], days: number): T[] {
  return items.slice(Math.max(0, items.length - days))
}

export function averageActualProduction(daily: readonly AnomalyDailyPoint[]): ProductionAverage {
  const values = daily
    .map((day) => toNumber(day.actual_production_kwh))
    .filter((value): value is number => value != null)

  if (values.length === 0) return { average: null, days: 0 }

  return {
    average: values.reduce((sum, value) => sum + value, 0) / values.length,
    days: values.length,
  }
}

export function productionPerformancePercent(daily: readonly AnomalyDailyPoint[]): ProductionPerformance {
  const totals = daily.reduce(
    (acc, day) => {
      const actual = toNumber(day.actual_production_kwh)
      const expected = toNumber(day.expected_production_kwh)
      if (actual == null || expected == null) return acc
      return {
        actual: acc.actual + actual,
        expected: acc.expected + expected,
        assessedDays: acc.assessedDays + 1,
      }
    },
    { actual: 0, expected: 0, assessedDays: 0 },
  )

  if (totals.expected <= 0 || totals.assessedDays === 0) return { percent: null, assessedDays: 0 }

  return {
    percent: (totals.actual / totals.expected) * 100,
    assessedDays: totals.assessedDays,
  }
}

function compareAgainstPreviousWindow(daily: readonly AnomalyDailyPoint[]): {
  dropPercent: number | null
  recentDays: number
} {
  const recent = latestProductionDays(daily, DEFAULT_PRODUCTION_PERIOD_DAYS)
  const previous = daily.slice(
    Math.max(0, daily.length - DEFAULT_PRODUCTION_PERIOD_DAYS * 2),
    Math.max(0, daily.length - DEFAULT_PRODUCTION_PERIOD_DAYS),
  )
  const recentAverage = averageActualProduction(recent)
  const previousAverage = averageActualProduction(previous)

  if (recentAverage.average == null || previousAverage.average == null || previousAverage.average <= 0) {
    return { dropPercent: null, recentDays: recentAverage.days }
  }

  return {
    dropPercent: ((recentAverage.average - previousAverage.average) / previousAverage.average) * 100,
    recentDays: recentAverage.days,
  }
}

export function compareProductionAverageTrend(
  daily: readonly AnomalyDailyPoint[],
  periodDays: ProductionPeriodDays,
): ProductionAverageTrend {
  const recent = latestProductionDays(daily, periodDays)
  const previous = daily.slice(
    Math.max(0, daily.length - periodDays * 2),
    Math.max(0, daily.length - periodDays),
  )
  const recentAverage = averageActualProduction(recent)
  const previousAverage = averageActualProduction(previous)

  if (recentAverage.average == null || previousAverage.average == null || previousAverage.average <= 0) {
    return {
      percent: null,
      tone: 'neutral',
      label: 'Sem comparação',
      detail: `Precisa de janela anterior de ${periodDays} dias para comparar tendência.`,
      recentAverage: recentAverage.average,
      previousAverage: previousAverage.average,
      recentDays: recentAverage.days,
      previousDays: previousAverage.days,
    }
  }

  const percent = ((recentAverage.average - previousAverage.average) / previousAverage.average) * 100

  if (percent <= HISTORICAL_CRITICAL_DROP_PERCENT) {
    return {
      percent,
      tone: 'danger',
      label: 'Queda forte',
      detail: `${formatNumber(Math.abs(percent), 1)}% abaixo da janela anterior.`,
      recentAverage: recentAverage.average,
      previousAverage: previousAverage.average,
      recentDays: recentAverage.days,
      previousDays: previousAverage.days,
    }
  }

  if (percent <= HISTORICAL_WARNING_DROP_PERCENT) {
    return {
      percent,
      tone: 'warning',
      label: 'Queda relevante',
      detail: `${formatNumber(Math.abs(percent), 1)}% abaixo da janela anterior.`,
      recentAverage: recentAverage.average,
      previousAverage: previousAverage.average,
      recentDays: recentAverage.days,
      previousDays: previousAverage.days,
    }
  }

  if (percent > 0) {
    return {
      percent,
      tone: 'success',
      label: 'Em recuperação',
      detail: `${formatNumber(percent, 1)}% acima da janela anterior.`,
      recentAverage: recentAverage.average,
      previousAverage: previousAverage.average,
      recentDays: recentAverage.days,
      previousDays: previousAverage.days,
    }
  }

  return {
    percent,
    tone: 'neutral',
    label: 'Estável',
    detail: `Variação de ${formatNumber(percent, 1)}% contra a janela anterior.`,
    recentAverage: recentAverage.average,
    previousAverage: previousAverage.average,
    recentDays: recentAverage.days,
    previousDays: previousAverage.days,
  }
}

// Regra operacional única para alerta de queda de produção:
// 1) Preferir desempenho contra esperado/baseline quando houver pares real+esperado.
// 2) Exigir ao menos 3 dias avaliados para reduzir ruído de um único dia.
// 3) Sem baseline, comparar média dos últimos 7 dias contra os 7 dias anteriores.
// Esses critérios seguem o padrão de mercado pesquisado: PR/esperado quando existe,
// histórico e disponibilidade como fallback quando a referência técnica ainda não fechou.
export function productionAlertSignal(daily: readonly AnomalyDailyPoint[]): ProductionAlertSignal {
  const recent = latestProductionDays(daily, DEFAULT_PRODUCTION_PERIOD_DAYS)
  const recentPerformance = productionPerformancePercent(recent)

  if (recentPerformance.percent != null && recentPerformance.assessedDays >= 3) {
    if (recentPerformance.percent < EXPECTED_CRITICAL_THRESHOLD_PERCENT) {
      return {
        tone: 'danger',
        label: 'Alerta crítico',
        detail: `Média de 7 dias em ${formatNumber(recentPerformance.percent, 1)}% do esperado.`,
      }
    }

    if (recentPerformance.percent < EXPECTED_WARNING_THRESHOLD_PERCENT) {
      return {
        tone: 'warning',
        label: 'Atenção',
        detail: `Média de 7 dias em ${formatNumber(recentPerformance.percent, 1)}% do esperado.`,
      }
    }

    return {
      tone: 'success',
      label: 'Dentro do gatilho',
      detail: `Média de 7 dias em ${formatNumber(recentPerformance.percent, 1)}% do esperado.`,
    }
  }

  const historical = compareAgainstPreviousWindow(daily)

  if (historical.dropPercent != null && historical.recentDays >= 3) {
    if (historical.dropPercent <= HISTORICAL_CRITICAL_DROP_PERCENT) {
      return {
        tone: 'danger',
        label: 'Alerta crítico',
        detail: `Média de 7 dias ${formatNumber(Math.abs(historical.dropPercent), 1)}% abaixo da janela anterior.`,
      }
    }

    if (historical.dropPercent <= HISTORICAL_WARNING_DROP_PERCENT) {
      return {
        tone: 'warning',
        label: 'Atenção',
        detail: `Média de 7 dias ${formatNumber(Math.abs(historical.dropPercent), 1)}% abaixo da janela anterior.`,
      }
    }

    return {
      tone: 'success',
      label: 'Dentro do gatilho',
      detail: `Sem queda relevante contra a janela anterior (${formatNumber(historical.dropPercent, 1)}%).`,
    }
  }

  return {
    tone: 'neutral',
    label: 'Aguardando dados',
    detail: 'Gatilho usa esperado/PR quando disponível; sem baseline, compara 7 dias contra a janela anterior.',
  }
}
