import type { ColumnSeriesItem } from './charts/ColumnSeries'
import { ColumnSeries } from './charts/ColumnSeries'
import { Card } from './Card'
import { EmptyState } from './EmptyState'
import type { MonthlyProductionHistoryResponse } from '../lib/dashboard/monthly-history-contracts'
import { formatCycleLabel, formatNumber } from '../lib/format'

// Seção "Produção por ciclo de faturamento": um `ColumnSeries` (kWh por
// ciclo fechado, colunas verticais em ordem cronológica — o tempo se lê da
// esquerda pra direita, mais compacto que a lista de barras horizontais
// anterior, ver ADR/instrução da troca). `history === null` é o estado de
// carregamento (mesmo padrão de `FinancialReturnSection`, cujo fetch/erro é
// dono do `DashboardPage`, não deste componente). Erro de rede/servidor é
// tratado fora daqui, isolado do resto da página, com `RetryableError` —
// este componente só recebe o resultado já parseado (ou `null` enquanto
// carrega).
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
      <EmptyState
        title="Sem ciclos fechados"
        description="Ainda não há ciclo de faturamento fechado para esta usina. Assim que a primeira fatura for consolidada, o histórico mensal aparecerá aqui."
        tone="neutral"
      />
    )
  }

  // `provisionalDays`/`incompleteDays` não disparam o selo de lacuna —
  // provisório ainda é medição real. Só `missingDays`/`unavailableDays`
  // (dias sem nenhum dado coletado) contam como lacuna de telemetria. Quando
  // há lacuna, `description` guarda a contagem EXATA de dias sem dado — o
  // `BarList` antigo só mostrava o selo "dados parciais" sem nunca expor
  // esse número em lugar nenhum da UI; a coluna nova preserva o selo E
  // acrescenta essa contagem (visível abaixo da coluna e na tabela `sr-only`
  // de `ColumnSeries`), nunca só em tooltip (ver instrução da tarefa).
  const items: ColumnSeriesItem[] = cycles.map((cycle) => {
    const gapDays =
      (cycle.quality?.missingDays ?? 0) + (cycle.quality?.unavailableDays ?? 0)
    const hasGap = cycle.quality != null && gapDays > 0
    return {
      label: formatCycleLabel(cycle.referenceMonth),
      value: cycle.productionKwh,
      unavailableLabel: 'sem dado',
      tone: hasGap ? 'warning' : 'neutral',
      ...(hasGap
        ? {
            badge: { label: 'dados parciais', tone: 'warning' as const },
            description: `${gapDays} ${gapDays === 1 ? 'dia' : 'dias'} sem dado`,
          }
        : {}),
    }
  })
  const hasAnyGap = items.some((item) => item.badge != null)

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Últimos {cyclesReturned} {cyclesReturned === 1 ? 'ciclo' : 'ciclos'}
      </p>
      <ColumnSeries
        className="mt-4"
        items={items}
        valueFormatter={(value) => `${formatNumber(value, 0)} kWh`}
        // Selo "dados parciais" é dado de qualidade real (ADR-038), não
        // decoração — a legenda só aparece quando pelo menos um ciclo tem
        // lacuna, para não poluir a leitura quando todos os ciclos exibidos
        // são completos.
        legend={
          hasAnyGap
            ? [{ label: 'Dados parciais — dias sem telemetria coletada', tone: 'warning', dashed: true }]
            : undefined
        }
      />
      {/* Uma coluna sozinha preenche 100% da escala e sugere uma comparação
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
