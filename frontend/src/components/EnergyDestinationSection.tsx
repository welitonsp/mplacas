import type { CycleQuality, ExecutiveIndicators } from '../lib/dashboard/contracts'
import { formatCycleLabel, formatNumber, toNumber } from '../lib/format'
import { EnergyFlowDiagram } from './EnergyFlowDiagram'
import { hasIncompleteDailyProduction } from './EnergyProductionSection'
import { SectionTitle } from './SectionTitle'

// "Para onde foi a energia" no ciclo da última fatura (ADR-083; o diagrama é
// o mesmo da antiga Visão Geral, ADR-077 item 14). Os percentuais vêm prontos
// do motor; a frase só os repete em português, nunca recalcula.
export function EnergyDestinationSection({
  indicators,
  quality,
  referenceMonth,
}: {
  indicators: ExecutiveIndicators
  quality: CycleQuality
  referenceMonth: string
}) {
  const selfSufficiency = toNumber(indicators.self_sufficiency_rate_percent)
  const consumption = toNumber(indicators.estimated_total_consumption_kwh)
  const imported = toNumber(indicators.imported_kwh)
  const cycle = formatCycleLabel(referenceMonth)

  return (
    <section className="mb-6" aria-labelledby="energy-destination-heading">
      <SectionTitle as="h2" id="energy-destination-heading">
        {`Para onde foi a energia — ciclo ${cycle}`}
      </SectionTitle>
      <div className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <EnergyFlowDiagram
          production={indicators.cycle_production_kwh}
          selfConsumption={indicators.estimated_self_consumption_kwh}
          injected={indicators.injected_kwh}
          imported={indicators.imported_kwh}
          consumption={indicators.estimated_total_consumption_kwh}
          partial={hasIncompleteDailyProduction(quality)}
          embedded
        />
        {selfSufficiency != null && consumption != null && (
          <p className="mt-5 border-t border-[var(--color-border)] pt-4 text-sm leading-6 text-[var(--color-text-primary)]">
            O sol supriu <strong>{formatNumber(selfSufficiency, 0)}%</strong> do consumo da casa
            {` (${formatNumber(consumption, 0)} kWh, estimado)`}
            {imported != null ? `; os outros ${formatNumber(imported, 0)} kWh vieram da rede.` : '.'}
          </p>
        )}
      </div>
    </section>
  )
}
