import type { MetricValue } from '../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../lib/format'
import { Card } from './Card'

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

  // Duas barras de composição (ADR-077, etapa 3) no lugar do Sankey: o nó
  // "Rede" do Sankey somava injetado + importado num número que não existe em
  // lugar nenhum da fatura e confundia a leitura. Cada barra responde UMA
  // pergunta, com os valores da fatura/motor na legenda. "estimado" continua
  // no consumo (achado A1): é inferido, nunca medido.
  // Cores com papel fixo: verde = energia do sol usada na casa; verde-claro =
  // excedente injetado; marinho = energia que veio da rede.
  const content = (
    <>
      {partial && (
        <span className="mb-4 inline-block rounded-full bg-[var(--color-warning-light)] px-2 py-0.5 text-xs font-semibold text-[var(--color-warning-text)]">
          Parcial
        </span>
      )}
      <div className="space-y-6">
        <CompositionBar
          title="Para onde foi a produção"
          total={production_}
          ariaLabel={`Produção de ${formatNumber(production_)} kWh: ${formatNumber(selfConsumption_)} kWh consumidos diretamente, ${formatNumber(injected_)} kWh injetados na rede.`}
          segments={[
            { label: 'Consumida na casa (estimado)', value: selfConsumption_, color: 'var(--color-energy-solar)' },
            { label: 'Injetada na rede', value: injected_, color: 'var(--color-energy-export)' },
          ]}
        />
        <CompositionBar
          title="De onde veio o consumo"
          qualifier="estimado"
          total={consumption_}
          ariaLabel={`Consumo estimado total de ${formatNumber(consumption_)} kWh: ${formatNumber(selfConsumption_)} kWh de produção própria, ${formatNumber(imported_)} kWh importados da rede.`}
          segments={[
            { label: 'Do sol', value: selfConsumption_, color: 'var(--color-energy-solar)' },
            { label: 'Da rede', value: imported_, color: 'var(--color-energy-grid)' },
          ]}
        />
      </div>
    </>
  )

  if (embedded) {
    return (
      <div
        data-testid="energy-flow-embedded"
        className={partial ? 'rounded-2xl border border-dashed border-[var(--color-warning)] p-4' : ''}
      >
        {content}
      </div>
    )
  }

  return <Card dashed={partial}>{content}</Card>
}

function CompositionBar({
  title,
  qualifier,
  total,
  ariaLabel,
  segments,
}: {
  title: string
  qualifier?: string
  total: number
  ariaLabel: string
  segments: ReadonlyArray<{ label: string; value: number; color: string }>
}) {
  const drawable = segments.filter((segment) => segment.value > 0)
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-semibold text-[var(--color-text-primary)]">
          {title}
          {qualifier && <span className="font-normal text-[var(--color-text-secondary)]"> ({qualifier})</span>}
        </p>
        <p className="shrink-0 font-display text-lg font-semibold tabular-nums text-[var(--color-text-primary)]">
          {formatNumber(total)}{' '}
          <span className="font-sans text-sm font-medium text-[var(--color-text-secondary)]">kWh</span>
        </p>
      </div>
      <div role="img" aria-label={ariaLabel} className="mt-2.5 flex h-3.5 w-full gap-[3px] overflow-hidden rounded-full">
        {drawable.map((segment) => (
          <span
            key={segment.label}
            aria-hidden="true"
            className="h-full first:rounded-l-full last:rounded-r-full"
            style={{ flex: `${segment.value} 1 0`, background: segment.color }}
          />
        ))}
      </div>
      <ul className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] text-[var(--color-text-secondary)]" aria-hidden="true">
        {segments.map((segment) => (
          <li key={segment.label} className="inline-flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-[3px]" style={{ background: segment.color }} />
            {segment.label}
            <span className="font-semibold tabular-nums text-[var(--color-text-primary)]">{formatNumber(segment.value)} kWh</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
