// Parser de `GET /energy/investor/latest` (ver `intelligence/router.py::
// _serialize_investor`, ADR-079). Valores monetários e taxas chegam como
// string (`Decimal`) e ficam como string; taxas são frações (0.1365 = 13,65%).

export type InvestorUnavailableReason =
  | 'INVESTMENT_NOT_REGISTERED'
  | 'COMMISSIONING_DATE_MISSING'
  | 'NO_CONSOLIDATED_SAVINGS'
  | 'MARKET_DATA_UNAVAILABLE'

export interface InvestorRealized {
  asOfMonth: string
  monthsElapsed: number
  accumulatedSavingsBrl: string
  cyclesCounted: number
  cdiPathNetBrl: string
  solarPathNetBrl: string
  cdiAccumulatedPercent: string
}

export interface PatrimonyPoint {
  year: number
  cdiPathBrl: string
  solarPathBrl: string
}

export interface InvestorProjection {
  baselineMonthlySavingsBrl: string
  irrPerYear: string | null
  irrRealPerYear: string | null
  cdiNetPerYear: string
  npvAtCdiNetBrl: string
  paybackSimpleMonths: number | null
  paybackDiscountedMonths: number | null
  lifetimeSavingsBrl: string
  wireBApplied: boolean
  patrimony: PatrimonyPoint[]
}

export interface InvestorPremises {
  cdiPerYear: string
  ipcaPerYear: string
  tariffGrowthPerYear: string
  horizonYears: number
  degradationPerYear: string
  omPerYearFraction: string
  inverterReplacementYear: number
  inverterReplacementFraction: string
  longTermIncomeTax: string
}

export interface InvestorPanel {
  plantId: string
  unavailableReason: InvestorUnavailableReason | null
  investmentBrl: string | null
  commissionedMonth: string | null
  monthsSinceCommissioning: number | null
  cyclesCounted: number
  calculationVersions: string[]
  includesPreCorrectionCycles: boolean
  lowConfidenceBaseline: boolean
  indices: { cdi12mPerYear: string | null; ipca12mPerYear: string | null; asOfMonth: string | null; source: string }
  realized: InvestorRealized | null
  projection: InvestorProjection | null
  premises: InvestorPremises | null
}

const REASONS: readonly InvestorUnavailableReason[] = [
  'INVESTMENT_NOT_REGISTERED',
  'COMMISSIONING_DATE_MISSING',
  'NO_CONSOLIDATED_SAVINGS',
  'MARKET_DATA_UNAVAILABLE',
]

type Rec = Record<string, unknown>

function isRecord(value: unknown): value is Rec {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function fail(key: string): never {
  throw new Error(`Resposta inválida da API: ${key}`)
}
function str(source: Rec, key: string): string {
  const value = source[key]
  if (typeof value !== 'string' || value.trim() === '') fail(key)
  return value
}
function strOrNull(source: Rec, key: string): string | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  fail(key)
}
function int(source: Rec, key: string): number {
  const value = source[key]
  if (typeof value === 'number' && Number.isInteger(value)) return value
  fail(key)
}
function intOrNull(source: Rec, key: string): number | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  return int(source, key)
}
function bool(source: Rec, key: string): boolean {
  const value = source[key]
  if (typeof value === 'boolean') return value
  fail(key)
}
function rec(source: Rec, key: string): Rec {
  const value = source[key]
  if (!isRecord(value)) fail(key)
  return value
}
function recOrNull(source: Rec, key: string): Rec | null {
  const value = source[key]
  if (value === null || value === undefined) return null
  if (!isRecord(value)) fail(key)
  return value
}

export function parseInvestorPanel(payload: unknown): InvestorPanel {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  const reason = strOrNull(payload, 'unavailable_reason')
  if (reason !== null && !(REASONS as readonly string[]).includes(reason)) fail('unavailable_reason')
  const versions = payload.calculation_versions
  if (!Array.isArray(versions) || !versions.every((v) => typeof v === 'string')) fail('calculation_versions')
  const indices = rec(payload, 'indices')
  const realized = recOrNull(payload, 'realized')
  const projection = recOrNull(payload, 'projection')
  const premises = recOrNull(payload, 'premises')

  let parsedProjection: InvestorProjection | null = null
  if (projection) {
    const patrimony = projection.patrimony
    if (!Array.isArray(patrimony)) fail('patrimony')
    parsedProjection = {
      baselineMonthlySavingsBrl: str(projection, 'baseline_monthly_savings_brl'),
      irrPerYear: strOrNull(projection, 'irr_per_year'),
      irrRealPerYear: strOrNull(projection, 'irr_real_per_year'),
      cdiNetPerYear: str(projection, 'cdi_net_per_year'),
      npvAtCdiNetBrl: str(projection, 'npv_at_cdi_net_brl'),
      paybackSimpleMonths: intOrNull(projection, 'payback_simple_months'),
      paybackDiscountedMonths: intOrNull(projection, 'payback_discounted_months'),
      lifetimeSavingsBrl: str(projection, 'lifetime_savings_brl'),
      wireBApplied: bool(projection, 'wire_b_applied'),
      patrimony: patrimony.map((point) => {
        if (!isRecord(point)) fail('patrimony[]')
        return {
          year: int(point, 'year'),
          cdiPathBrl: str(point, 'cdi_path_brl'),
          solarPathBrl: str(point, 'solar_path_brl'),
        }
      }),
    }
  }

  return {
    plantId: str(payload, 'plant_id'),
    unavailableReason: reason as InvestorUnavailableReason | null,
    investmentBrl: strOrNull(payload, 'investment_brl'),
    commissionedMonth: strOrNull(payload, 'commissioned_month'),
    monthsSinceCommissioning: intOrNull(payload, 'months_since_commissioning'),
    cyclesCounted: int(payload, 'cycles_counted'),
    calculationVersions: versions as string[],
    includesPreCorrectionCycles: bool(payload, 'includes_pre_correction_cycles'),
    lowConfidenceBaseline: bool(payload, 'low_confidence_baseline'),
    indices: {
      cdi12mPerYear: strOrNull(indices, 'cdi_12m_per_year'),
      ipca12mPerYear: strOrNull(indices, 'ipca_12m_per_year'),
      asOfMonth: strOrNull(indices, 'as_of_month'),
      source: str(indices, 'source'),
    },
    realized: realized
      ? {
          asOfMonth: str(realized, 'as_of_month'),
          monthsElapsed: int(realized, 'months_elapsed'),
          accumulatedSavingsBrl: str(realized, 'accumulated_savings_brl'),
          cyclesCounted: int(realized, 'cycles_counted'),
          cdiPathNetBrl: str(realized, 'cdi_path_net_brl'),
          solarPathNetBrl: str(realized, 'solar_path_net_brl'),
          cdiAccumulatedPercent: str(realized, 'cdi_accumulated_percent'),
        }
      : null,
    projection: parsedProjection,
    premises: premises
      ? {
          cdiPerYear: str(premises, 'cdi_per_year'),
          ipcaPerYear: str(premises, 'ipca_per_year'),
          tariffGrowthPerYear: str(premises, 'tariff_growth_per_year'),
          horizonYears: int(premises, 'horizon_years'),
          degradationPerYear: str(premises, 'degradation_per_year'),
          omPerYearFraction: str(premises, 'om_per_year_fraction'),
          inverterReplacementYear: int(premises, 'inverter_replacement_year'),
          inverterReplacementFraction: str(premises, 'inverter_replacement_fraction'),
          longTermIncomeTax: str(premises, 'long_term_income_tax'),
        }
      : null,
  }
}
