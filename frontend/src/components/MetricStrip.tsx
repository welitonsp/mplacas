import type { MetricValue } from '../lib/dashboard/contracts'
import { clampPercent, formatNumber } from '../lib/format'
import { Card } from './Card'

export interface MetricStripItem {
  label: string
  value: MetricValue
  unit?: string
  // Mesmo propósito de `MetricCard.maximumFractionDigits` (ex.: tarifas em
  // R$/kWh, ver ADR-056) — cada item da tira decide sua própria precisão,
  // sem herdar um padrão global.
  maximumFractionDigits?: number
  // Mesma barra de progresso de `MetricCard.barPercent` — só o item que a
  // recebe desenha a barra; os outros ficam sem (ex.: só "Cobertura de
  // créditos" tem barra hoje, ver `FinancialSection`).
  barPercent?: number | null
}

// Tira compacta de métricas pequenas e correlacionadas (ex.: tarifas com/sem
// impostos + saldo/cobertura de créditos), lado a lado dentro de um único
// `Card` — em vez de um `MetricCard` (um `Card` cada) por métrica. Existe
// porque várias métricas pequenas alinhadas viravam tantas "caixas" quanto um
// dado principal do dashboard (mesmo peso visual do custo do ciclo que elas
// só complementam) — ver skill frontend-design e ADR-072 Etapa 7
// (`FinancialSection`, compactação de tarifas/créditos). Rótulo, valor,
// unidade e formatação de cada item são idênticos ao `MetricCard`
// equivalente — só o invólucro (um `Card` por item vira uma coluna dentro de
// um `Card` só) muda.
//
// Estados por item (cada `MetricStripItem` decide os seus, independente dos
// outros itens da mesma tira):
// - valor presente: número formatado (`formatNumber`) + unidade, se houver.
// - valor `null`: traço "—" (mesmo fallback de `MetricCard`/`formatNumber`),
//   nunca "0" nem a coluna some — a ausência de dado continua visível.
// - `barPercent` informado: barra de progresso com semântica ARIA
//   (`role="progressbar"`, `aria-valuenow/min/max`), igual `MetricCard`.
// - `barPercent` omitido: sem barra, só rótulo/valor/unidade.
//
// Grade fixa em 4 colunas (`sm:grid-cols-4`, 2 em telas estreitas) — classes
// Tailwind precisam ser literais no código-fonte para o build gerar o CSS
// correspondente (nunca construídas em runtime via template string, ver
// skill frontend-design, seção Build). `FinancialSection` usa duas tiras, 2
// itens cada — tarifas dentro de "Custo do ciclo", saldo/cobertura de
// créditos em "Créditos de energia" (blocos separados por grandeza, achado
// F3 da auditoria financeira desta sessão) — ambas cabendo dentro da mesma
// grade de até 4 colunas, sem sobra de linha. Se um futuro consumidor
// precisar de mais de 4 itens, adicione uma nova classe literal aqui em vez
// de interpolar `items.length`.
export function MetricStrip({ items, className = '' }: { items: MetricStripItem[]; className?: string }) {
  return (
    <Card className={`grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-6 ${className}`.trim()}>
      {items.map((item) => (
        <div key={item.label}>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{item.label}</p>
          <p className="mt-2 text-lg font-semibold text-gray-900 tabular-nums sm:text-2xl">
            {formatNumber(item.value, item.maximumFractionDigits)}
            {item.unit && <span className="ml-1 text-sm font-normal text-gray-500">{item.unit}</span>}
          </p>
          {item.barPercent != null && (
            <div
              className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-chart-track)]"
              role="progressbar"
              aria-valuenow={clampPercent(item.barPercent)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={item.label}
            >
              <div
                className="h-full rounded-full bg-[var(--color-brand-primary)]"
                style={{ width: `${clampPercent(item.barPercent)}%` }}
              />
            </div>
          )}
        </div>
      ))}
    </Card>
  )
}
