import type { AnomalyFetchState } from '../lib/dashboard/contracts'
import { latestNonNullProductionDate } from '../lib/dashboard/contracts'
import { levelSeverity } from '../lib/dashboard/visuals'
import { formatFullDate, formatNumber, toNumber } from '../lib/format'
import { Bullet } from './charts/Bullet'
import { Card } from './Card'

// Compara a produção real do ÚLTIMO DIA com dado diário coletado contra a
// produção esperada do mesmo dia — ambas na mesma escala diária (kWh/dia).
// Substituiu a comparação anterior entre `indicators.cycle_production_kwh`
// (total do ciclo, ~30 dias) e a produção esperada (média diária): comparar
// essas duas grandezas direto produzia um desvio percentual absurdo (~2900%).
// A produção do ciclo continua visível em "Fluxo de energia"
// (`EnergyFlowDiagram`) — não foi perdida, só parou de ser comparada contra
// uma expectativa de outra escala (ver DashboardPage).
export function LatestDailyProductionCard({
  anomalyState,
  className,
}: {
  anomalyState: AnomalyFetchState
  className?: string
}) {
  const loading = anomalyState.loading && !anomalyState.data

  if (loading) {
    return (
      <Card className={`animate-pulse ${className ?? ''}`.trim()}>
        <div className="mb-3 h-3 w-1/3 rounded bg-gray-200" />
        <div className="h-8 w-full rounded bg-gray-100" />
      </Card>
    )
  }

  const daily = anomalyState.data?.daily ?? []
  const latestDate = latestNonNullProductionDate(daily)
  const latestPoint = latestDate ? (daily.find((d) => d.date === latestDate) ?? null) : null
  const actualValue = latestPoint ? toNumber(latestPoint.actual_production_kwh) : null

  // Nenhum dia com produção real coletada ainda (usina nova, backfill
  // pendente, ou falha ao carregar o histórico) — estado indisponível
  // explícito, nunca uma barra fabricada a partir de zero.
  if (!latestPoint || actualValue == null) {
    return (
      <Card className={className}>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Produção do último dia vs. esperada
        </p>
        <p className="mt-4 text-sm text-gray-500">
          Ainda não há produção diária registrada para comparar com o esperado.
        </p>
      </Card>
    )
  }

  // `expected_production_kwh` pode vir `null` mesmo com produção real presente
  // (ex.: usina sem coordenadas configuradas nesse dia) — `Bullet` já trata
  // `target: null` desenhando só a barra real, sem tick e sem desvio fabricado.
  const expectedValue = toNumber(latestPoint.expected_production_kwh)
  const tone = levelSeverity(latestPoint.level)

  return (
    <Card className={className}>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Produção de {formatFullDate(latestPoint.date)} vs. esperada
      </p>
      <div className="mt-4">
        <Bullet
          value={actualValue}
          target={expectedValue}
          valueFormatter={(n) => `${formatNumber(n)} kWh`}
          targetLabel="esperado"
          tone={tone}
        />
      </div>
    </Card>
  )
}
