import type { PerformanceUnavailableReason, PhotovoltaicPerformanceLatest } from '../lib/dashboard/photovoltaic-contracts'
import { performanceUnavailableMessage, ratioToPercent } from '../lib/dashboard/photovoltaic-contracts'
import { performanceSeverity } from '../lib/dashboard/visuals'
import { formatNumber } from '../lib/format'
import { Card } from './Card'
import { Gauge } from './charts/Gauge'

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
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Performance ratio (PR)</p>
        <p className="mt-4 text-sm text-gray-500">
          {performanceUnavailableMessage(unavailableReason ?? 'NO_PERFORMANCE_RESULTS')}
        </p>
      </Card>
    )
  }

  const pr = ratioToPercent(performance.performance_ratio)
  const prCorrected = ratioToPercent(performance.temperature_corrected_performance_ratio)

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Performance ratio (PR)</p>
      <div className="mt-3 flex items-start justify-around gap-4">
        <PrGauge value={pr} label="Bruto" />
        <PrGauge value={prCorrected} label="Corrigido por temperatura" />
      </div>
      <p className="mt-3 text-xs text-gray-500">
        O PR bruto compara produção real com o que a irradiância do dia permitiria. O corrigido
        por temperatura desconta o efeito do calor nas células, então isola melhor problemas que
        não são clima.
      </p>
    </Card>
  )
}

// `value` chega como `null` quando o backend não conseguiu calcular a razão
// (ex.: sem POA térmico modelado para o PR corrigido) — nesse caso não faz
// sentido desenhar um anel de 0%, que sugeriria "performou zero", então
// mostramos um placeholder neutro sem valor fabricado.
function PrGauge({ value, label }: { value: number | null; label: string }) {
  if (value === null) {
    return (
      <div className="inline-flex flex-col items-center" style={{ width: 72 }}>
        <div
          className="flex items-center justify-center rounded-full border-2 border-dashed border-[var(--color-chart-track)] text-sm font-semibold text-gray-500"
          style={{ width: 72, height: 72 }}
        >
          —
        </div>
        <p className="mt-1 text-center text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      </div>
    )
  }

  return (
    <Gauge
      value={value}
      label={label}
      valueLabel={`${formatNumber(value, 0)}%`}
      tone={performanceSeverity(value)}
      size={72}
    />
  )
}
