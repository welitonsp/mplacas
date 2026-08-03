import type { CycleQuality, ExecutiveIndicators } from '../lib/dashboard/contracts'
import { MetricCard } from './MetricCard'
import { ProductionSplitCard } from './ProductionSplitCard'

// Só os indicadores derivados do dado diário de geração (`cycle_production_kwh` e
// tudo que é calculado a partir dele — ver `reconcile_bill` em
// `billing/models.py`) podem ficar incompletos quando o ciclo tem
// `missing_days`/`provisional_days`/`incomplete_days`/`unavailable_days`.
// `imported_kwh` e `injected_kwh` vêm da FATURA CONFIRMADA, não do dado diário —
// marcá-los como "Parcial" seria factualmente errado (ver diagnóstico da Etapa 2).
function hasIncompleteDailyProduction(quality: CycleQuality): boolean {
  return (
    quality.missing_days + quality.provisional_days + quality.incomplete_days + quality.unavailable_days > 0
  )
}

export function EnergyProductionSection({
  indicators,
  quality,
}: {
  indicators: ExecutiveIndicators
  quality: CycleQuality
}) {
  const partial = hasIncompleteDailyProduction(quality)

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <MetricCard
        label="Produção no ciclo"
        value={indicators.cycle_production_kwh}
        unit="kWh"
        partial={partial}
      />
      <MetricCard label="Energia importada" value={indicators.imported_kwh} unit="kWh" />
      <MetricCard label="Energia injetada" value={indicators.injected_kwh} unit="kWh" />
      <MetricCard
        label="Autoconsumo estimado"
        value={indicators.estimated_self_consumption_kwh}
        unit="kWh"
        partial={partial}
      />
      <MetricCard
        label="Consumo total estimado"
        value={indicators.estimated_total_consumption_kwh}
        unit="kWh"
        partial={partial}
      />
      <ProductionSplitCard
        selfConsumption={indicators.estimated_self_consumption_kwh}
        injected={indicators.injected_kwh}
      />
    </div>
  )
}
