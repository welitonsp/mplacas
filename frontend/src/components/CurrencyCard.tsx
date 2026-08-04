import type { MetricValue } from '../lib/dashboard/contracts'
import { formatCurrency } from '../lib/format'
import { Card } from './Card'

// Valor financeiro é dado neutro, não destaque promocional — mesmo esqueleto
// visual do `MetricCard` padrão (branco, borda cinza sutil), só com a
// formatação de moeda diferente (ver Etapa 8).
export function CurrencyCard({ label, value }: { label: string; value: MetricValue }) {
  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900 tabular-nums">{formatCurrency(value)}</p>
    </Card>
  )
}
