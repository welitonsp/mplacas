import type { MetricValue } from '../lib/dashboard/contracts'
import { savingsUnavailableMessage } from '../lib/dashboard/contracts'
import { formatCurrency } from '../lib/format'
import { Card } from './Card'

// Economia estimada do ciclo (ver
// intelligence/energy_engine.py::analyze_energy_cycle para a fórmula exata).
// Quando a fatura do ciclo não tem tarifa com impostos registrada, o backend
// manda `value: null` com `unavailableReason` preenchido — este card nunca
// deve renderizar "R$ 0,00" nesse caso, só a mensagem explícita do motivo
// (mesmo princípio de `ExpectedProductionCard`/`baselineUnavailableMessage`).
export function EstimatedSavingsCard({
  value,
  unavailableReason,
}: {
  value: MetricValue
  unavailableReason: string | null
}) {
  if (unavailableReason != null) {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Economia estimada</p>
        <p className="mt-4 text-sm text-gray-500">{savingsUnavailableMessage(unavailableReason)}</p>
      </Card>
    )
  }

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Economia estimada</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900 tabular-nums">{formatCurrency(value)}</p>
    </Card>
  )
}
