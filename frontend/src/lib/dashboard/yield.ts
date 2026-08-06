import type { AnomalyDailyPoint } from './contracts'
import { toNumber } from '../format'

// A produção diária esperada usada como referência para o cálculo de anomalias
// (GET /energy/anomalies/latest) deixou de ser uma constante fixa: vem do baseline
// sazonal real da usina, calculado e quantizado inteiramente no backend
// (`photovoltaic/expected_production.py`, ADR-068) e lido via
// `GET /photovoltaic/summary` — ver
// `lib/dashboard/photovoltaic-contracts.ts::parsePhotovoltaicSummary`.

// Rendimento = produção real (kWh) / irradiância (kWh/m²) — kWh gerados por
// cada kWh/m² de sol recebido. É a métrica que separa "problema na usina" de
// "estava nublado": produção baixa com irradiância baixa é dia nublado (normal),
// produção baixa com irradiância alta é problema real. Calculado 100% no
// frontend a partir do `daily` que a API já retorna — sem endpoint novo.
export interface DayYieldInfo {
  date: string
  yieldValue: number
  deviationPercent: number
}

export interface YieldStats {
  periodYield: number | null
  days: DayYieldInfo[]
}

// Limiar para marcar um dia como "rendimento atípico" em relação à média do
// período. Referência: os dois exemplos reais desta usina que motivaram a
// feature têm desvio de -33% e +27% — 20% cobre esses casos com folga sem
// sinalizar ruído normal de dia a dia.
export const YIELD_ATYPICAL_THRESHOLD_PERCENT = 20

export function computeYieldStats(daily: AnomalyDailyPoint[]): YieldStats {
  const pairs = daily
    .map((d) => ({
      date: d.date,
      actual: toNumber(d.actual_production_kwh),
      irradiation: toNumber(d.irradiation_kwh_m2),
    }))
    .filter(
      (p): p is { date: string; actual: number; irradiation: number } =>
        p.actual != null && p.actual > 0 && p.irradiation != null && p.irradiation > 0
    )

  if (pairs.length === 0) return { periodYield: null, days: [] }

  const totalActual = pairs.reduce((sum, p) => sum + p.actual, 0)
  const totalIrradiation = pairs.reduce((sum, p) => sum + p.irradiation, 0)
  if (totalIrradiation <= 0) return { periodYield: null, days: [] }

  const periodYield = totalActual / totalIrradiation
  const days = pairs.map((p) => {
    const yieldValue = p.actual / p.irradiation
    const deviationPercent = ((yieldValue - periodYield) / periodYield) * 100
    return { date: p.date, yieldValue, deviationPercent }
  })

  return { periodYield, days }
}
