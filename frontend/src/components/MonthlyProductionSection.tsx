import type { BarListItem } from './charts/BarList'
import { BarList } from './charts/BarList'
import { Card } from './Card'
import type { MonthlyProductionHistoryResponse } from '../lib/dashboard/monthly-history-contracts'
import { formatCycleLabel, formatNumber } from '../lib/format'

// Seção "Produção por ciclo de faturamento": um `BarList` (kWh por ciclo
// fechado, ordem cronológica, nunca reordenado — ver skill `chart-standards`).
// `history === null` é o estado de carregamento (mesmo padrão de
// `FinancialReturnSection`, cujo fetch/erro é dono do `DashboardPage`, não
// deste componente). Erro de rede/servidor é tratado fora daqui, isolado do
// resto da página, com `RetryableError` — este componente só recebe o
// resultado já parseado (ou `null` enquanto carrega).
export function MonthlyProductionSection({
  history,
}: {
  history: MonthlyProductionHistoryResponse | null
}) {
  if (history === null) {
    return (
      <Card className="animate-pulse">
        <div className="h-3 w-1/3 rounded bg-gray-200" />
        <div className="mt-4 h-24 w-full rounded bg-gray-100" />
      </Card>
    )
  }

  const { cycles, cyclesReturned } = history

  // Usina nova sem nenhum ciclo com fatura confirmada — estado normal, não
  // erro (o backend devolve `200` com `cycles: []`, ver contrato do endpoint).
  if (cycles.length === 0) {
    return (
      <Card>
        <p className="text-sm text-gray-500">
          Ainda não há ciclo de faturamento fechado para esta usina.
        </p>
      </Card>
    )
  }

  // `provisionalDays`/`incompleteDays` não disparam o selo de lacuna —
  // provisório ainda é medição real. Só `missingDays`/`unavailableDays`
  // (dias sem nenhum dado coletado) contam como lacuna de telemetria.
  const items: BarListItem[] = cycles.map((cycle) => {
    const hasGap =
      cycle.quality != null &&
      (cycle.quality.missingDays ?? 0) + (cycle.quality.unavailableDays ?? 0) > 0
    return {
      label: formatCycleLabel(cycle.referenceMonth),
      value: cycle.productionKwh,
      unavailableLabel: 'sem dado',
      tone: hasGap ? 'warning' : 'neutral',
      ...(hasGap ? { badge: { label: 'dados parciais', tone: 'warning' as const } } : {}),
    }
  })

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Últimos {cyclesReturned} {cyclesReturned === 1 ? 'ciclo' : 'ciclos'}
      </p>
      <BarList
        className="mt-4"
        items={items}
        valueFormatter={(value) => `${formatNumber(value, 0)} kWh`}
      />
      {/* Uma barra sozinha preenche 100% da escala e sugere uma comparação
          que não existe — a ressalva evita que o usuário leia "cheio" como
          "bom" sem nada para comparar (ver instrução da tarefa). */}
      {cycles.length === 1 && (
        <p className="mt-3 text-xs text-gray-500">
          Comparação disponível a partir do segundo ciclo fechado.
        </p>
      )}
    </Card>
  )
}
