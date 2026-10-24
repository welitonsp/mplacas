import { useState } from 'react'
import { Card } from './Card'
import { EmptyState } from './EmptyState'
import { LoadingAnnouncement } from './LoadingAnnouncement'
import type { MonthlyProductionCycle, MonthlyProductionHistoryResponse } from '../lib/dashboard/monthly-history-contracts'
import type { MonthlyReportExportFormat } from '../lib/api'
import { downloadMonthlyReportExport } from '../lib/api'
import { formatCycleLabel, formatNumber, formatShortDate } from '../lib/format'

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
        className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--color-brand-primary)] px-4 text-sm font-semibold text-[var(--color-on-brand)] shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-[var(--color-brand-primary-dark)] hover:shadow-md active:translate-y-0 focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-primary)] focus:ring-offset-2 focus:ring-offset-[var(--color-surface)] focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-sm motion-reduce:transition-none"
      >
        {downloading && (
          <span
            aria-hidden="true"
            className="h-3.5 w-3.5 rounded-full border-2 border-current/40 border-t-current animate-spin"
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

// Ciclo a ciclo da fatura: quanto as PLACAS geraram (inversor) ao lado do que a
// distribuidora registrou no mesmo período (ADR-083, etapa 3 — "o mais
// importante é saber quanto as placas geraram no período do ciclo × o período
// da operadora"). A injeção só é chamada de "medidor" quando o backend afirma
// (`gridInjectionBasis === 'METER'`, ADR-078); senão é a linha de injeção da
// fatura, que no layout atual é a energia compensada. "Ficou na casa" é
// estimativa do motor (placas − injeção) e aparece como tal. Dias sem leitura
// estimados pelo sol (ADR-082) aparecem — nunca somem nem viram "medido".
// `history === null` = carregando.
function gapDescription(gapDays: number, estimatedDays: number): string {
  const base = `${gapDays} ${gapDays === 1 ? 'dia' : 'dias'} sem leitura do inversor`
  if (estimatedDays <= 0) return base
  return `${base}, ${estimatedDays === gapDays ? 'estimados' : `${estimatedDays} estimados`} pelo sol`
}

const VISIBLE_CYCLES = 6

const DISTRIBUTOR_NAMES: Readonly<Record<string, string>> = {
  EQUATORIAL_GO: 'Equatorial',
}

// Nome curto da distribuidora pelo código da fatura; código desconhecido ou
// ausente vira "distribuidora", nunca um nome inventado.
export function distributorDisplayName(code: string | null | undefined): string {
  return (code && DISTRIBUTOR_NAMES[code]) || 'distribuidora'
}

function kwh(value: number): string {
  return `${formatNumber(value, 0)} kWh`
}

function cyclePeriod(cycle: MonthlyProductionCycle): string | null {
  if (!cycle.cycleStart || !cycle.cycleEnd) return null
  return `${formatShortDate(cycle.cycleStart)} a ${formatShortDate(cycle.cycleEnd)}`
}

function Bar({ value, max, className }: { value: number | null; max: number; className: string }) {
  // Zero desenha zero: só valor positivo ganha a largura mínima visível.
  const width = value == null || value <= 0 || max <= 0 ? 0 : Math.max(2, Math.round((value / max) * 100))
  return (
    <span aria-hidden="true" className="block h-2.5 w-full overflow-hidden rounded-full bg-[var(--color-chart-track)]">
      <span className={`block h-full rounded-full ${className}`} style={{ width: `${width}%` }} />
    </span>
  )
}

// Linha de uma `dl`: o `div` só agrupa `dt` + `dd` (modelo de conteúdo de
// `dl`); a barra decorativa mora dentro do `dd`, junto do valor.
function MeterLine({ label, value, max, barClassName }: { label: string; value: number | null; max: number; barClassName: string }) {
  return (
    <div className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)] items-center gap-3">
      <dt className="text-[13px] text-[var(--color-text-secondary)]">{label}</dt>
      <dd className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
        <Bar value={value} max={max} className={barClassName} />
        <span className="text-right text-[14px] font-semibold tabular-nums text-[var(--color-text-primary)]">
          {value == null ? 'sem registro' : kwh(value)}
        </span>
      </dd>
    </div>
  )
}

function CycleRow({ cycle, max }: { cycle: MonthlyProductionCycle; max: number }) {
  const gapDays = (cycle.quality?.missingDays ?? 0) + (cycle.quality?.unavailableDays ?? 0)
  const period = cyclePeriod(cycle)
  const label = formatCycleLabel(cycle.referenceMonth)
  const distributor = distributorDisplayName(cycle.distributor)
  const metered = cycle.gridInjectionBasis === 'METER'
  const injectionLabel = metered ? `Medidor da ${distributor}` : 'Injeção na fatura'
  return (
    <li className="flex flex-col gap-2 border-t border-[var(--color-border)] py-4 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-[15px] font-semibold text-[var(--color-text-primary)]">
          {label}
          {period && <span className="ml-2 text-[13px] font-normal text-[var(--color-text-secondary)]">{period}</span>}
        </h3>
        {gapDays > 0 && (
          <span className="rounded-full bg-[var(--color-warning-light)] px-2 py-0.5 text-xs font-semibold text-[var(--color-warning-text)]">
            {gapDescription(gapDays, cycle.quality?.estimatedDays ?? 0)}
          </span>
        )}
      </div>
      <dl className="grid grid-cols-1 gap-2">
        <MeterLine label="Placas geraram" value={cycle.productionKwh} max={max} barClassName="bg-[var(--color-energy-solar)]" />
        <MeterLine label={injectionLabel} value={cycle.gridInjectionKwh} max={max} barClassName="bg-[var(--color-energy-grid)]" />
      </dl>
      {cycle.gridInjectionKwh != null && !metered && (
        <p className="text-xs leading-5 text-[var(--color-text-secondary)]">
          Não é a leitura do medidor: é a linha de injeção da fatura, que pode ser só a energia compensada. Se for, o
          enviado à rede foi maior e o que ficou na casa, menor que o estimado.
        </p>
      )}
      {(cycle.selfConsumptionKwh != null || cycle.importedKwh != null) && (
        <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">
          {cycle.selfConsumptionKwh != null && (
            <>
              Ficou na casa (estimado): <strong className="font-semibold text-[var(--color-text-primary)]">{kwh(cycle.selfConsumptionKwh)}</strong>
            </>
          )}
          {cycle.selfConsumptionKwh != null && cycle.importedKwh != null && ' · '}
          {cycle.importedKwh != null && <>Veio da rede: <strong className="font-semibold text-[var(--color-text-primary)]">{kwh(cycle.importedKwh)}</strong></>}
        </p>
      )}
    </li>
  )
}

export function MonthlyProductionSection({
  history,
  plantId,
}: {
  history: MonthlyProductionHistoryResponse | null
  plantId: string
}) {
  const [showAll, setShowAll] = useState(false)

  if (history === null) {
    return (
      <Card className="animate-pulse">
        <LoadingAnnouncement active message="Carregando ciclos da fatura" />
        <div className="h-3 w-1/3 rounded bg-gray-200" />
        <div className="mt-4 h-24 w-full rounded bg-gray-100" />
      </Card>
    )
  }

  // Usina nova sem nenhum ciclo com fatura confirmada — estado normal, não
  // erro (o backend devolve `200` com `cycles: []`, ver contrato do endpoint).
  if (history.cycles.length === 0) {
    return (
      <EmptyState
        title="Sem ciclos fechados"
        description="Ainda não há ciclo de faturamento fechado para esta usina. Assim que a primeira fatura for confirmada, a comparação entre as placas e a distribuidora aparece aqui."
        tone="neutral"
      />
    )
  }

  // Mais recente primeiro: é o ciclo da última fatura que o dono compara.
  const newestFirst = [...history.cycles].reverse()
  const visible = showAll ? newestFirst : newestFirst.slice(0, VISIBLE_CYCLES)
  const max = Math.max(
    1,
    ...history.cycles.map((cycle) => cycle.productionKwh ?? 0),
    ...history.cycles.map((cycle) => cycle.gridInjectionKwh ?? 0),
  )

  return (
    <Card>
      <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">
        No período exato de cada fatura: o que as placas geraram (inversor) e o que a {distributorDisplayName(newestFirst[0]?.distributor)}{' '}
        registrou como enviado à rede. O que ficou na casa é estimado pela diferença entre os dois.
      </p>
      <ul className="mt-4">
        {visible.map((cycle) => (
          <CycleRow key={cycle.billId} cycle={cycle} max={max} />
        ))}
      </ul>
      {newestFirst.length > VISIBLE_CYCLES && (
        <button
          type="button"
          onClick={() => setShowAll((value) => !value)}
          aria-expanded={showAll}
          className="mt-2 inline-flex min-h-[44px] items-center rounded text-sm font-semibold text-[var(--color-brand-primary)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
        >
          {showAll ? 'Mostrar só os mais recentes' : `Ver os ${newestFirst.length} ciclos`}
        </button>
      )}
      <MonthlyExportControl plantId={plantId} />
    </Card>
  )
}
