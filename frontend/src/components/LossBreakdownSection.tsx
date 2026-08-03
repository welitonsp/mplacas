import type { LossesUnavailableReason, PhotovoltaicLossItem } from '../lib/dashboard/photovoltaic-contracts'
import { lossesUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { EVIDENCE_LEVEL_META, LOSS_CATEGORY_LABEL, SEVERITY_BG, SEVERITY_TEXT } from '../lib/dashboard/visuals'
import { formatNumber, toNumber } from '../lib/format'

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
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Por que produzi menos</p>
        <p className="mt-4 text-sm text-gray-500">
          {lossesUnavailableMessage(unavailableReason ?? 'NO_LOSS_ASSESSMENTS')}
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Por que produzi menos</p>
      <ul className="mt-3 space-y-2">
        {losses.map((item) => {
          const meta = EVIDENCE_LEVEL_META[item.evidence_level]
          const lossValue = toNumber(item.estimated_loss_percent)
          return (
            <li
              key={item.category}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-gray-100 p-3"
            >
              <div>
                <p className="text-sm font-medium text-gray-800">{LOSS_CATEGORY_LABEL[item.category]}</p>
                <span
                  className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${SEVERITY_BG[meta.severity]} ${SEVERITY_TEXT[meta.severity]}`}
                >
                  {meta.label}
                </span>
                {item.limitation && <p className="mt-1 text-xs text-gray-500">{item.limitation}</p>}
              </div>
              <p className="text-sm font-semibold text-gray-900">
                {formatNumber(lossValue)}
                <span className="ml-1 text-xs font-normal text-gray-500">%</span>
              </p>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
