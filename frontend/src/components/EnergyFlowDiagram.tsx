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
  embedded = false,
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
  embedded?: boolean
}) {
  const prod = toNumber(production)
  const sc = toNumber(selfConsumption)
  const inj = toNumber(injected)
  const imp = toNumber(imported)
  const cons = toNumber(consumption)

  const hasData = prod != null && prod > 0 && cons != null && cons > 0 && sc != null && inj != null && imp != null

  if (!hasData) {
    if (embedded) {
      return <p className="rounded-2xl py-8 text-center text-sm text-gray-500">Dados insuficientes para o diagrama.</p>
    }
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

  const content = (
    <>
      {partial && (
        <span className="absolute right-3 top-3 rounded-full bg-[var(--color-warning-light)] px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-warning)]">
          Parcial
        </span>
      )}
      <SankeyFlow
        nodes={[
          { id: 'production', label: 'Produção', value: production_ },
          { id: 'grid', label: 'Rede', value: injected_ + imported_ },
          // "estimado" no rótulo (achado A1 do audit de honestidade de dado):
          // `consumption_` é `estimated_total_consumption_kwh`, inferido a partir
          // de `cycle_production_kwh - injected_kwh` (ver `billing/models.py`),
          // nunca medido diretamente — ao contrário de "Produção" e "Rede"
          // (soma de `injected_kwh`/`imported_kwh`, ambos da fatura confirmada).
          // O rótulo aparece tanto no nó do SVG quanto na linha correspondente da
          // tabela `sr-only` (`SankeyFlow` reusa o mesmo `label`), então este é o
          // único lugar que precisa do qualificador para cobrir os dois.
          { id: 'consumption', label: 'Consumo estimado', value: consumption_ },
        ]}
        flows={[
          // Composição (para onde a energia foi), não severidade de bom/ruim —
          // achado M3 do audit: autoconsumo alto não é "bom" nem injeção alta na
          // rede é "ruim", os três fluxos só descrevem como a produção se
          // distribuiu. Por isso os três usam o mesmo tom neutro (equivalente a
          // `--color-brand-primary`); `tone: 'success'` era usado aqui por engano
          // no fluxo de autoconsumo.
          { from: 'production', to: 'consumption', value: selfConsumption_, tone: 'neutral' },
          { from: 'production', to: 'grid', value: injected_, tone: 'neutral' },
          { from: 'grid', to: 'consumption', value: imported_, tone: 'neutral' },
        ]}
        valueFormatter={valueFormatter}
      />

      <p className="mt-3 text-xs text-gray-500">
        {formatNumber(selfConsumption_)} kWh de autoconsumo estimado e{' '}
        {formatNumber(injected_)} kWh injetados na rede a partir da produção de{' '}
        {formatNumber(production_)} kWh. Consumo total estimado de {formatNumber(consumption_)} kWh, sendo{' '}
        {formatNumber(imported_)} kWh importados da rede.
      </p>
    </>
  )

  if (embedded) {
    return (
      <div
        data-testid="energy-flow-embedded"
        className={`relative rounded-2xl ${partial ? 'border border-dashed border-[var(--color-warning)] p-4' : ''}`}
      >
        {content}
      </div>
    )
  }

  return <Card dashed={partial}>{content}</Card>
}
