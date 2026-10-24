import { useState } from 'react'
import { Check, CircleHelp, OctagonAlert, TriangleAlert, type LucideIcon } from 'lucide-react'
import { Card } from './Card'
import { EmptyState } from './EmptyState'
import { LoadingAnnouncement } from './LoadingAnnouncement'
import type {
  MonthlyProductionCycle,
  MonthlyProductionHistoryResponse,
  UtilityCheck,
  UtilityCheckVerdict,
} from '../lib/dashboard/monthly-history-contracts'
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

// Placas × distribuidora, ciclo a ciclo, com a conferência (ADR-083 etapa 3 e
// ADR-084). Responde "estou tendo prejuízo?" sem enganar:
// - o medidor da distribuidora só registra o que SAI para a rede; o que a casa
//   consome na hora nunca passa por ele. Por isso a produção é mostrada
//   dividida em "rede" (registrado) e "casa" (estimado), e não como perda;
// - o veredito vem do backend (`utilityCheck`): créditos que sumiram
//   (prejuízo comprovado), envio maior que a produção (impossível) ou fração
//   enviada fora do padrão (suspeita). Sem dado, "sem conferência" — nunca OK.
// A injeção só é "medidor" quando o backend afirma (`gridInjectionBasis`).
// `history === null` = carregando.

const VISIBLE_CYCLES = 6

const DISTRIBUTOR_NAMES: Readonly<Record<string, string>> = {
  EQUATORIAL_GO: 'Equatorial',
}

// Nome curto da distribuidora pelo código da fatura; código desconhecido ou
// ausente vira "distribuidora", nunca um nome inventado.
export function distributorDisplayName(code: string | null | undefined): string {
  return (code && DISTRIBUTOR_NAMES[code]) || 'distribuidora'
}

function kwh(value: number, digits = 0): string {
  return `${formatNumber(value, digits)} kWh`
}

function gapDescription(gapDays: number, estimatedDays: number): string {
  const base = `${gapDays} ${gapDays === 1 ? 'dia' : 'dias'} sem leitura do inversor`
  if (estimatedDays <= 0) return base
  return `${base}, ${estimatedDays === gapDays ? 'estimados' : `${estimatedDays} estimados`} pelo sol`
}

function cyclePeriod(cycle: MonthlyProductionCycle): string | null {
  if (!cycle.cycleStart || !cycle.cycleEnd) return null
  return `${formatShortDate(cycle.cycleStart)} a ${formatShortDate(cycle.cycleEnd)}`
}

type Tone = 'success' | 'warning' | 'danger' | 'neutral'

const VERDICT_META: Record<UtilityCheckVerdict, { label: string; tone: Tone; icon: LucideIcon }> = {
  OK: { label: 'Sem sinal de prejuízo', tone: 'success', icon: Check },
  SUSPECT: { label: 'Fora do padrão', tone: 'warning', icon: TriangleAlert },
  IMPOSSIBLE: { label: 'Registro impossível', tone: 'danger', icon: OctagonAlert },
  LOSS: { label: 'Créditos faltando', tone: 'danger', icon: OctagonAlert },
  UNVERIFIABLE: { label: 'Sem conferência', tone: 'neutral', icon: CircleHelp },
}

const TONE_TEXT: Record<Tone, string> = {
  success: 'text-[var(--color-success-text)]',
  warning: 'text-[var(--color-warning-text)]',
  danger: 'text-[var(--color-danger-text)]',
  neutral: 'text-[var(--color-text-secondary)]',
}

const TONE_SURFACE: Record<Tone, string> = {
  success: 'bg-[var(--color-success-light)] text-[var(--color-success-text)]',
  warning: 'bg-[var(--color-warning-light)] text-[var(--color-warning-text)]',
  danger: 'bg-[var(--color-danger-light)] text-[var(--color-danger-text)]',
  neutral: 'bg-[var(--color-gray-100)] text-[var(--color-text-secondary)]',
}

const TONE_DOT: Record<Tone, string> = {
  success: 'bg-[var(--color-success)]',
  warning: 'bg-[var(--color-warning)]',
  danger: 'bg-[var(--color-danger)]',
  neutral: 'bg-[var(--color-gray-400)]',
}

// Frase única do veredito, com os números que o provam.
export function verdictDetail(cycle: MonthlyProductionCycle, distributor: string): string {
  const check = cycle.utilityCheck
  if (!check) return 'Conferência ainda não disponível para este ciclo.'
  switch (check.verdict) {
    case 'LOSS':
      return `A fatura não mostra ${kwh(check.missingCreditsKwh ?? 0, 2)} nem como abatimento nem como saldo. Confira com a ${distributor}: crédito expira após 5 anos e pode ter ido para outra unidade do rateio.`
    case 'IMPOSSIBLE':
      return `A ${distributor} registrou ${kwh(cycle.gridInjectionKwh ?? 0)} enviados à rede, mais do que o inversor produziu${cycle.productionKwh != null ? ` (${kwh(cycle.productionKwh)})` : ''}. Um dos dois medidores está errado: vale pedir aferição.`
    case 'SUSPECT':
      return `Só ${formatNumber(check.exportSharePercent ?? 0, 0)}% da produção foi para a rede, contra ${formatNumber(check.exportShareBaselinePercent ?? 0, 0)}% no seu histórico. Pode ser o medidor ou mais consumo durante o dia.`
    case 'OK':
      return check.creditsAvailableKwh != null && check.creditsUsedKwh != null && check.creditBalanceKwh != null
        ? `Todo kWh registrado virou crédito: ${kwh(check.creditsAvailableKwh, 2)} disponíveis, ${kwh(check.creditsUsedKwh, 2)} usados, saldo de ${kwh(check.creditBalanceKwh, 2)}.`
        : 'Todo kWh registrado virou crédito.'
    default:
      if (check.reasons.includes('NO_METER_READING')) return 'A fatura deste ciclo não traz a leitura do medidor de geração.'
      if (check.reasons.includes('NO_PREVIOUS_BILL')) return 'Falta a fatura do mês anterior para conferir o saldo de créditos.'
      return 'Não há dados suficientes para conferir este ciclo.'
  }
}

function VerdictBadge({ check }: { check: UtilityCheck | null }) {
  const meta = VERDICT_META[check?.verdict ?? 'UNVERIFIABLE']
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${TONE_TEXT[meta.tone]}`}>
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[meta.tone]}`} />
      {meta.label}
    </span>
  )
}

// Composição da produção: o que foi para a rede (registrado) e o que ficou na
// casa (estimado). Uma barra fina, 100% = produção do ciclo.
function ProductionSplit({ cycle }: { cycle: MonthlyProductionCycle }) {
  const production = cycle.productionKwh
  const grid = cycle.gridInjectionKwh
  if (production == null || production <= 0 || grid == null) return null
  const gridShare = Math.min(100, Math.max(0, (grid / production) * 100))
  return (
    <span aria-hidden="true" className="flex h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-energy-solar-light)]">
      <span className="h-full bg-[var(--color-energy-grid)]" style={{ width: `${gridShare}%` }} />
    </span>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-[var(--color-text-secondary)]">{label}</dt>
      <dd className="mt-0.5">
        <span className="block whitespace-nowrap text-[15px] font-semibold tabular-nums text-[var(--color-text-primary)]">{value}</span>
        {hint && <span className="block text-xs text-[var(--color-text-secondary)]">{hint}</span>}
      </dd>
    </div>
  )
}

function CycleRow({ cycle }: { cycle: MonthlyProductionCycle }) {
  const gapDays = (cycle.quality?.missingDays ?? 0) + (cycle.quality?.unavailableDays ?? 0)
  const period = cyclePeriod(cycle)
  const distributor = distributorDisplayName(cycle.distributor)
  const metered = cycle.gridInjectionBasis === 'METER'
  return (
    <li className="flex flex-col gap-3 border-t border-[var(--color-border)] py-5 first:border-t-0 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-[15px] font-semibold text-[var(--color-text-primary)]">
          {formatCycleLabel(cycle.referenceMonth)}
          {period && <span className="ml-2 text-[13px] font-normal text-[var(--color-text-secondary)]">{period}</span>}
        </h3>
        <VerdictBadge check={cycle.utilityCheck} />
      </div>
      <ProductionSplit cycle={cycle} />
      <dl className="grid grid-cols-3 gap-3">
        <Stat
          label="Produziu"
          value={cycle.productionKwh == null ? 'sem registro' : kwh(cycle.productionKwh)}
          hint={cycle.productionKwh == null ? undefined : 'inversor'}
        />
        <Stat
          label="Rede"
          value={cycle.gridInjectionKwh == null ? 'sem registro' : kwh(cycle.gridInjectionKwh)}
          hint={cycle.gridInjectionKwh == null ? undefined : metered ? `medidor ${distributor}` : 'linha da fatura'}
        />
        <Stat
          label="Casa"
          value={cycle.selfConsumptionKwh == null ? 'sem registro' : kwh(cycle.selfConsumptionKwh)}
          hint={cycle.selfConsumptionKwh == null ? undefined : 'estimado'}
        />
      </dl>
      <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">
        {verdictDetail(cycle, distributor)}
        {cycle.gridInjectionKwh != null && !metered &&
          ' O número da rede não é a leitura do medidor: pode ser só a energia compensada, e aí a casa ficou com menos que o estimado.'}
      </p>
      {gapDays > 0 && (
        <p className="text-xs font-medium text-[var(--color-warning-text)]">{gapDescription(gapDays, cycle.quality?.estimatedDays ?? 0)}</p>
      )}
    </li>
  )
}

// Veredito da janela inteira, no topo: a resposta em uma linha.
function Summary({ cycles }: { cycles: MonthlyProductionCycle[] }) {
  const distributor = distributorDisplayName(cycles[cycles.length - 1]?.distributor)
  const byVerdict = (verdict: UtilityCheckVerdict) => cycles.filter((cycle) => cycle.utilityCheck?.verdict === verdict)
  const loss = byVerdict('LOSS')
  const impossible = byVerdict('IMPOSSIBLE')
  const suspect = byVerdict('SUSPECT')
  const ok = byVerdict('OK')
  const plural = (count: number) => (count === 1 ? 'ciclo' : 'ciclos')

  let tone: Tone
  let title: string
  let detail: string
  if (loss.length > 0) {
    const missing = loss.reduce((sum, cycle) => sum + (cycle.utilityCheck?.missingCreditsKwh ?? 0), 0)
    tone = 'danger'
    title = `${kwh(missing, 2)} de créditos faltando`
    detail = `Em ${loss.length} ${plural(loss.length)}, a fatura não mostra todo kWh registrado como abatimento ou saldo.`
  } else if (impossible.length > 0) {
    tone = 'danger'
    title = 'Registro impossível'
    detail = `Em ${impossible.length} ${plural(impossible.length)}, a ${distributor} registrou mais envio à rede do que o inversor produziu.`
  } else if (suspect.length > 0) {
    tone = 'warning'
    title = 'Ciclo fora do padrão'
    detail = `Em ${suspect.length} ${plural(suspect.length)}, a fração enviada à rede caiu muito em relação ao seu histórico.`
  } else if (ok.length > 0) {
    tone = 'success'
    title = 'Sem sinal de prejuízo'
    detail = `Conferimos ${ok.length} ${plural(ok.length)}: todo kWh que a ${distributor} registrou virou crédito.`
  } else {
    tone = 'neutral'
    title = 'Ainda sem conferência'
    detail = 'Assim que houver duas faturas seguidas com a leitura do medidor, a conferência aparece aqui.'
  }
  const Icon = VERDICT_META[tone === 'success' ? 'OK' : tone === 'warning' ? 'SUSPECT' : tone === 'danger' ? 'LOSS' : 'UNVERIFIABLE'].icon
  return (
    <div className="flex items-start gap-4">
      <span aria-hidden="true" className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${TONE_SURFACE[tone]}`}>
        <Icon size={20} strokeWidth={2.25} />
      </span>
      <div className="min-w-0">
        <p className={`font-display text-[20px] font-semibold leading-7 ${tone === 'neutral' ? 'text-[var(--color-text-primary)]' : TONE_TEXT[tone]}`}>
          {title}
        </p>
        <p className="mt-0.5 text-[14px] leading-5 text-[var(--color-text-secondary)]">{detail}</p>
      </div>
    </div>
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

  return (
    <Card className="sm:p-6">
      <Summary cycles={history.cycles} />
      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-[var(--color-border)] pt-4 text-xs text-[var(--color-text-secondary)]">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-[var(--color-energy-grid)]" />
          Rede: o que o medidor da distribuidora registra
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-[var(--color-energy-solar-light)] ring-1 ring-[var(--color-energy-solar)]" />
          Casa: consumido na hora, não passa pelo medidor
        </span>
      </div>
      <ul className="mt-5">
        {visible.map((cycle) => (
          <CycleRow key={cycle.billId} cycle={cycle} />
        ))}
      </ul>
      {newestFirst.length > VISIBLE_CYCLES && (
        <button
          type="button"
          onClick={() => setShowAll((value) => !value)}
          aria-expanded={showAll}
          className="mt-3 inline-flex min-h-[44px] items-center rounded text-sm font-semibold text-[var(--color-brand-primary)] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
        >
          {showAll ? 'Mostrar só os mais recentes' : `Ver os ${newestFirst.length} ciclos`}
        </button>
      )}
      <MonthlyExportControl plantId={plantId} />
    </Card>
  )
}
