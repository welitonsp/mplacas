import type { MetricValue } from '../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../lib/format'
import { Card } from './Card'
import { SankeyFlow } from './charts/SankeyFlow'

// Este componente NÃO carrega mais seu próprio rótulo "Fluxo de energia no
// ciclo" — até a faixa de estado do módulo Visão Geral (ver
// `pages/dashboard/OverviewPage.tsx`), o rótulo aparecia duas vezes seguidas
// (a sobrancelha interna aqui + o `<SectionTitle as="h2">Fluxo de
// energia</SectionTitle>` que o chamador já renderiza logo acima), uma das 4
// duplicações apontadas pelo diagnóstico de UX que motivou aquela mudança.
// Removida a interna: é só um `<p>` visual (sem papel de heading no outline
// de acessibilidade), enquanto o `<h2>` do chamador É a âncora semântica real
// — mantê-lo e descartar a duplicata visual preserva o outline de heading e
// remove a repetição de texto. Único consumidor deste componente hoje é
// `OverviewPage` (confirmado via grep antes desta mudança); se um segundo
// consumidor aparecer sem heading externo, prefira que ELE renderize um
// `SectionTitle` próprio a reintroduzir um rótulo interno aqui.
export function EnergyFlowDiagram({
  production,
  selfConsumption,
  injected,
  imported,
  consumption,
  partial = false,
}: {
  production: MetricValue
  selfConsumption: MetricValue
  injected: MetricValue
  imported: MetricValue
  consumption: MetricValue
  // Autoconsumo/consumo/produção vêm do dado diário e podem ficar incompletos
  // quando o ciclo tem `missing_days`/`provisional_days`/`incomplete_days`/
  // `unavailable_days` (ver `hasIncompleteDailyProduction` em
  // `EnergyProductionSection`). Importada/injetada vêm da fatura confirmada,
  // nunca parciais — por isso o selo cobre o diagrama inteiro (que mistura os
  // dois), não um nó isolado. Absorve o selo "Parcial" que antes só existia
  // nos cards removidos de "Energia e produção" (ver P2-01, Etapa 3.3).
  partial?: boolean
}) {
  const prod = toNumber(production)
  const sc = toNumber(selfConsumption)
  const inj = toNumber(injected)
  const imp = toNumber(imported)
  const cons = toNumber(consumption)

  const hasData = prod != null && prod > 0 && cons != null && cons > 0 && sc != null && inj != null && imp != null

  if (!hasData) {
    return (
      <Card>
        <p className="text-sm text-gray-500">Dados insuficientes para o diagrama.</p>
      </Card>
    )
  }

  const production_ = prod as number
  const consumption_ = cons as number
  const selfConsumption_ = sc as number
  const injected_ = inj as number
  const imported_ = imp as number

  const valueFormatter = (value: number) => `${formatNumber(value)} kWh`

  return (
    <Card dashed={partial}>
      {partial && (
        <span className="absolute right-3 top-3 rounded-full bg-[var(--color-warning-light)] px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-warning)]">
          Parcial
        </span>
      )}
      <SankeyFlow
        nodes={[
          { id: 'production', label: 'Produção', value: production_ },
          { id: 'grid', label: 'Rede', value: injected_ + imported_ },
          { id: 'consumption', label: 'Consumo', value: consumption_ },
        ]}
        flows={[
          { from: 'production', to: 'consumption', value: selfConsumption_, tone: 'success' },
          { from: 'production', to: 'grid', value: injected_, tone: 'neutral' },
          { from: 'grid', to: 'consumption', value: imported_, tone: 'neutral' },
        ]}
        valueFormatter={valueFormatter}
      />

      <p className="mt-3 text-xs text-gray-500">
        {formatNumber(selfConsumption_)} kWh consumidos diretamente e{' '}
        {formatNumber(injected_)} kWh injetados na rede a partir da produção de{' '}
        {formatNumber(production_)} kWh. Consumo total de {formatNumber(consumption_)} kWh, sendo{' '}
        {formatNumber(imported_)} kWh importados da rede.
      </p>
    </Card>
  )
}
