import type { ExecutiveIndicators } from '../lib/dashboard/contracts'
import { formatCurrency, formatNumber, toNumber, formatCycleLabel } from '../lib/format'
import { Card } from './Card'
import { SectionTitle } from './SectionTitle'

// "Sua conta com e sem a usina" — a pergunta que o dono da usina mais faz.
// Todos os números vêm prontos do backend (`intelligence/energy_engine.py`,
// versão de cálculo 0.4.0); aqui só se apresenta. A conta sem a usina usa a
// tarifa cheia homologada (ADR-080), informada no selo do card. O padrão segue o das
// plataformas de mercado (Arcadia/Genability): a fatura SEM solar é o mesmo
// ciclo recalculado com todo o consumo comprado da rede, e o modelo é
// conferido contra a fatura real antes de se confiar na economia.
//
// Sem tarifa no ciclo os campos vêm `null` e o card não aparece — o
// `SavingsUnavailableCard` (`FinancialSection`) explica o motivo, sem R$ 0,00
// fabricado.

const BILL_MATCH_TOLERANCE_BRL = 0.05

function BillBar({
  label,
  value,
  max,
  tone,
}: {
  label: string
  value: number
  max: number
  tone: 'muted' | 'brand'
}) {
  const percent = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-[var(--color-text-secondary)]">{label}</span>
        <span
          className={`font-display tabular-nums font-semibold ${
            tone === 'brand' ? 'text-[24px] text-[var(--color-text-primary)]' : 'text-[20px] text-[var(--color-text-secondary)]'
          }`}
        >
          {formatCurrency(value)}
        </span>
      </div>
      <div className="mt-2 h-3 w-full overflow-hidden rounded-full bg-[var(--color-chart-track)]" aria-hidden="true">
        <div
          className={`h-full rounded-full ${
            tone === 'brand' ? 'bg-[var(--color-energy-solar)]' : 'bg-[var(--color-chart-reference)]'
          }`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  )
}

function Detail({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[13px] font-medium leading-5 text-[var(--color-text-secondary)]">{label}</dt>
      <dd className="mt-0.5 text-[15px] font-semibold tabular-nums text-[var(--color-text-primary)]">{value}</dd>
      {note && <dd className="text-xs leading-5 text-[var(--color-text-secondary)]">{note}</dd>}
    </div>
  )
}

export function BillComparisonCard({
  indicators,
  referenceMonth,
}: {
  indicators: ExecutiveIndicators
  referenceMonth: string
}) {
  const withoutSolar = toNumber(indicators.bill_without_solar_brl ?? null)
  const paid = toNumber(indicators.total_amount_brl)
  const savings = toNumber(indicators.estimated_savings_brl)
  if (withoutSolar == null || paid == null || savings == null) return null

  const max = Math.max(withoutSolar, paid)
  const savingsTariff = toNumber(indicators.savings_tariff_brl_kwh ?? null)
  const source = indicators.savings_tariff_source ?? null
  // Sem o campo (backend anterior ao ADR-080), nada é afirmado sobre a tarifa.
  const tariffLabel =
    source === 'DISTRIBUTOR_FULL_TARIFF'
      ? savingsTariff == null
        ? 'Com a tarifa cheia da distribuidora'
        : `Com a tarifa cheia da distribuidora: R$ ${formatNumber(savingsTariff, 3)}/kWh com impostos`
      : source === 'BILL_TARIFF'
        ? 'Com a tarifa da própria fatura: pode subestimar a economia'
        : null
  const excess = toNumber(indicators.excess_credit_kwh ?? null)
  const creditValue = toNumber(indicators.credit_balance_value_brl ?? null)
  const difference = toNumber(indicators.bill_model_difference_brl ?? null)
  // Quanto da energia que veio da rede foi paga com créditos (percentual do
  // motor, `credit_coverage_rate_percent`). Abaixo de 100%, o resto saiu pela
  // tarifa cheia — o que mais encarece a conta (ex.: fatura de out/26).
  const coverage = toNumber(indicators.credit_coverage_rate_percent)
  const compensated = toNumber(indicators.compensated_kwh ?? null)
  const imported = toNumber(indicators.imported_kwh)

  let matchText: string
  let matchNote: string | undefined
  if (difference == null) {
    matchText = 'Indisponível'
    matchNote = 'A fatura deste ciclo não trouxe a tarifa do Fio B.'
  } else if (Math.abs(difference) <= BILL_MATCH_TOLERANCE_BRL) {
    matchText = 'Confere com o valor cobrado'
    matchNote = 'Diferença de centavos entre o cálculo e a fatura.'
  } else if (difference > 0) {
    matchText = `${formatCurrency(difference)} de outros itens`
    matchNote = 'Cobrado além do cálculo. Pode ser custo mínimo, retroativo ou multa: confira a fatura.'
  } else {
    matchText = `${formatCurrency(Math.abs(difference))} a menos`
    matchNote = 'A fatura veio abaixo do cálculo. Pode ser desconto ou devolução: confira a fatura.'
  }

  return (
    <section className="md:col-span-6 lg:col-span-12" aria-labelledby="bill-comparison-heading">
      <SectionTitle as="h2" id="bill-comparison-heading">
        Sua conta com e sem a usina
      </SectionTitle>
      <Card className="sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">
              Economia no ciclo {formatCycleLabel(referenceMonth)}
            </p>
            <p className="mt-1 font-display text-[32px] font-semibold leading-tight tabular-nums text-[var(--color-success-text)]">
              {formatCurrency(savings)}
            </p>
          </div>
          {tariffLabel && (
            <span className="inline-flex rounded-md bg-[var(--color-surface-subtle)] px-2 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
              {tariffLabel}
            </span>
          )}
        </div>

        <div className="mt-5 space-y-4">
          <BillBar label="Sem a usina, você pagaria" value={withoutSolar} max={max} tone="muted" />
          <BillBar label="Com a usina, você pagou" value={paid} max={max} tone="brand" />
        </div>

        <dl className="mt-6 grid grid-cols-1 gap-x-6 gap-y-4 border-t border-[var(--color-border)] pt-5 sm:grid-cols-2 xl:grid-cols-3">
          <Detail
            label="Consumo da casa no ciclo"
            value={`${formatNumber(indicators.estimated_total_consumption_kwh, 0)} kWh`}
            note="Da rede + direto do telhado (pelo inversor)."
          />
          <Detail
            label="Energia que saiu para a rede"
            value={`${formatNumber(indicators.injected_kwh, 0)} kWh`}
            note={
              excess != null && excess > 0
                ? `${formatNumber(excess, 0)} kWh passaram do consumo e viraram crédito.`
                : undefined
            }
          />
          <Detail
            label="Créditos guardados"
            value={`${formatNumber(indicators.credit_balance_kwh, 2)} kWh`}
            note={creditValue != null ? `Valem cerca de ${formatCurrency(creditValue)}, já descontado o Fio B.` : undefined}
          />
          {coverage != null && (
            <Detail
              label="Pago com créditos"
              value={`${formatNumber(coverage, 0)}% da energia da rede`}
              note={
                compensated != null && imported != null
                  ? `${formatNumber(compensated, 0)} de ${formatNumber(imported, 0)} kWh.${
                      coverage < 100 ? ' O resto foi cobrado pela tarifa cheia.' : ''
                    }`
                  : coverage < 100
                    ? 'O resto foi cobrado pela tarifa cheia.'
                    : undefined
              }
            />
          )}
          <Detail label="Conferência com a fatura" value={matchText} note={matchNote} />
        </dl>
      </Card>
    </section>
  )
}
