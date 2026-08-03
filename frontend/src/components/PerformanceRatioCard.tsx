import type { PerformanceUnavailableReason, PhotovoltaicPerformanceLatest } from '../lib/dashboard/photovoltaic-contracts'
import { performanceUnavailableMessage, ratioToPercent } from '../lib/dashboard/photovoltaic-contracts'
import { formatNumber } from '../lib/format'

// PR (performance ratio) mede o quanto a usina produziu em relação ao que a
// irradiância recebida permitiria, sem descontar o efeito da temperatura nas
// células. O PR corrigido por temperatura (`temperature_corrected_performance_ratio`,
// só existe quando o POA térmico foi modelado — `performance.py`) isola esse
// efeito, então os dois números lado a lado respondem perguntas diferentes:
// "quão bem a usina performou hoje" vs. "quão bem ela performou descontando o
// calor do dia". Ambos chegam do backend como razão 0–1 (`units_json:
// performance_ratio = "ratio"`) — convertidos aqui para percentual (ver
// `ratioToPercent`).
export function PerformanceRatioCard({
  performance,
  unavailableReason,
}: {
  performance: PhotovoltaicPerformanceLatest | null
  unavailableReason: PerformanceUnavailableReason | null
}) {
  if (performance === null) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Performance ratio (PR)</p>
        <p className="mt-4 text-sm text-gray-500">
          {performanceUnavailableMessage(unavailableReason ?? 'NO_PERFORMANCE_RESULTS')}
        </p>
      </div>
    )
  }

  const pr = ratioToPercent(performance.performance_ratio)
  const prCorrected = ratioToPercent(performance.temperature_corrected_performance_ratio)

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Performance ratio (PR)</p>
      <div className="mt-2 grid grid-cols-2 gap-4">
        <div>
          <p className="text-2xl font-semibold text-gray-900">
            {formatNumber(pr)}
            <span className="ml-1 text-sm font-normal text-gray-500">%</span>
          </p>
          <p className="mt-1 text-xs text-gray-500">Bruto</p>
        </div>
        <div>
          <p className="text-2xl font-semibold text-gray-900">
            {formatNumber(prCorrected)}
            <span className="ml-1 text-sm font-normal text-gray-500">%</span>
          </p>
          <p className="mt-1 text-xs text-gray-500">Corrigido por temperatura</p>
        </div>
      </div>
      <p className="mt-3 text-xs text-gray-500">
        O PR bruto compara produção real com o que a irradiância do dia permitiria. O corrigido
        por temperatura desconta o efeito do calor nas células, então isola melhor problemas que
        não são clima.
      </p>
    </div>
  )
}
