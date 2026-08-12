import { useState } from 'react'
import type { ColumnSeriesItem } from './charts/ColumnSeries'
import { ColumnSeries } from './charts/ColumnSeries'
import { Card } from './Card'
import { EmptyState } from './EmptyState'
import { LoadingAnnouncement } from './LoadingAnnouncement'
import type { MonthlyProductionHistoryResponse } from '../lib/dashboard/monthly-history-contracts'
import type { MonthlyReportExportFormat } from '../lib/api'
import { downloadMonthlyReportExport } from '../lib/api'
import { formatCycleLabel, formatNumber } from '../lib/format'

const EXPORT_FORMAT_LABELS: Record<MonthlyReportExportFormat, string> = {
  pdf: 'PDF',
  xlsx: 'XLSX',
  csv: 'CSV',
}

// Exportação síncrona do relatório mensal mais recente já fechado (T2, plano
// de auditoria 2026-08-12) — `GET /reports/monthly/latest.<formato>`
// (`reports/router.py:107,130,153`). O pipeline assíncrono (`POST
// /monthly/exports` + polling) fica fora de escopo: o plano manda começar
// pelo síncrono. Estado local porque a ação não alimenta mais nada da
// página — nenhum outro bloco depende do resultado do download.
function MonthlyExportControl({ plantId }: { plantId: string }) {
  const [format, setFormat] = useState<MonthlyReportExportFormat>('pdf')
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleExport() {
    setError(null)
    setDownloading(true)
    try {
      await downloadMonthlyReportExport(plantId, format)
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : 'Não foi possível gerar o relatório. Tente novamente.'
      )
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="mt-4 flex flex-col gap-3 border-t border-[var(--color-border)] pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
      <div className="flex items-center gap-2">
        <label htmlFor="monthly-export-format" className="text-xs font-medium text-gray-600">
          Exportar relatório do ciclo mais recente
        </label>
        <select
          id="monthly-export-format"
          value={format}
          onChange={(event) => setFormat(event.target.value as MonthlyReportExportFormat)}
          disabled={downloading}
          className="min-h-[44px] rounded-lg border border-gray-300 px-2 py-1.5 text-xs text-gray-900 transition-colors duration-150 focus:border-[var(--color-brand-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-primary)] focus-visible:ring-2 disabled:opacity-50"
        >
          <option value="pdf">PDF</option>
          <option value="xlsx">XLSX</option>
          <option value="csv">CSV</option>
        </select>
      </div>
      <button
        type="button"
        onClick={handleExport}
        disabled={downloading}
        aria-busy={downloading}
        className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--color-brand-primary)] px-4 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-[var(--color-brand-primary-dark)] hover:shadow-md active:translate-y-0 focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-primary)] focus:ring-offset-2 focus:ring-offset-[var(--color-surface)] focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-sm motion-reduce:transition-none"
      >
        {downloading && (
          <span
            aria-hidden="true"
            className="h-3.5 w-3.5 rounded-full border-2 border-white/45 border-t-white animate-spin"
          />
        )}
        {downloading ? `Gerando ${EXPORT_FORMAT_LABELS[format]}...` : `Baixar ${EXPORT_FORMAT_LABELS[format]}`}
      </button>
      <LoadingAnnouncement
        active={downloading}
        message={`Gerando arquivo ${EXPORT_FORMAT_LABELS[format]}, aguarde.`}
      />
      {error && (
        <p role="alert" className="w-full text-xs text-[var(--color-danger-text)]">
          {error}
        </p>
      )}
    </div>
  )
}

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
  plantId,
}: {
  history: MonthlyProductionHistoryResponse | null
  plantId: string
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
      <MonthlyExportControl plantId={plantId} />
    </Card>
  )
}
