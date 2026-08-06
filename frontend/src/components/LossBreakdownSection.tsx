import type { LossesUnavailableReason, PhotovoltaicLossItem } from '../lib/dashboard/photovoltaic-contracts'
import { lossesUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { EVIDENCE_LEVEL_META, LOSS_CATEGORY_LABEL } from '../lib/dashboard/visuals'
import { formatNumber, toNumber } from '../lib/format'
import type { BarListItem } from './charts/BarList'
import { BarList } from './charts/BarList'
import { Card } from './Card'

// "Por que produzi menos": as oito categorias fixas da taxonomia de perdas
// (`loss_taxonomy.py::LossCategory`), sempre na ordem devolvida pelo backend
// — nunca reordenadas por severidade (ver ADR-065 seção 4, `estimated_loss_percent`
// e `evidence_level` sempre exibidos juntos para não apresentar um proxy como
// perda medida, ex.: COMMUNICATION mede reporte ausente, não energia perdida).
export function LossBreakdownSection({
  losses,
  unavailableReason,
}: {
  losses: PhotovoltaicLossItem[] | null
  unavailableReason: LossesUnavailableReason | null
}) {
  if (losses === null) {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Por que produzi menos</p>
        <p className="mt-4 text-sm text-gray-500">
          {lossesUnavailableMessage(unavailableReason ?? 'NO_LOSS_ASSESSMENTS')}
        </p>
      </Card>
    )
  }

  // `BarList` nunca reordena os itens que recebe — a ordem de `losses` (a
  // mesma devolvida pelo backend) é preservada 1:1 aqui, item a item.
  const items: BarListItem[] = losses.map((item) => {
    const meta = EVIDENCE_LEVEL_META[item.evidence_level]
    const lossValue = toNumber(item.estimated_loss_percent)
    return {
      label: LOSS_CATEGORY_LABEL[item.category],
      // `estimated_loss_percent: null` (NOT_ASSESSABLE ou NOT_DETECTED sem
      // estimativa numérica) nunca vira barra de 0% fabricada — `BarList`
      // desenha um estado neutro nesse caso (ver `BarListItem.value`).
      value: lossValue,
      tone: meta.severity,
      badge: { label: meta.label, tone: meta.severity },
      description: item.limitation ?? undefined,
    }
  })

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Por que produzi menos</p>
      <BarList
        className="mt-3"
        items={items}
        maxValue={100}
        valueFormatter={(value) => `${formatNumber(value, 1)}%`}
      />
    </Card>
  )
}
