import type { ExecutiveIndicators } from '../lib/dashboard/contracts'
import { savingsUnavailableMessage } from '../lib/dashboard/contracts'
import type { FinancialReturnResponse } from '../lib/dashboard/financial-return-contracts'
import type { PlantResource } from '../hooks/usePlantResource'
import { formatCurrency, formatCycleLabel, formatNumber, toNumber } from '../lib/format'
import { SectionTitle } from './SectionTitle'
import { StackedBar } from './charts/StackedBar'
import { BillComparisonCard } from './BillComparisonCard'
import { FinancialReturnSection } from './FinancialReturnSection'
import { RetryableError } from './RetryableError'
import { Card } from './Card'

// Aba Dinheiro (ADR-083, etapa 2) — "quanto ganhei?", do horizonte longo para
// o detalhe:
// 1. Retorno do investimento (quanto a usina já devolveu);
// 2. A conta do último ciclo com e sem a usina (BillComparisonCard);
// 3. Detalhes da fatura, recolhidos: decomposição do valor e as duas tarifas
//    da fatura, com o que cada uma significa.
// Usina × CDI e Faturas ficam em `FinancialPage`, depois deste bloco.
//
// Saíram (ADR-083, regra "cada número uma vez por tela"): a faixa "Resumo
// financeiro" (repetia economia, ROI, payback e cobertura), o painel genérico
// "Decisão financeira" e o bloco "Créditos de energia" (o saldo já está na
// conta do ciclo, e a cobertura virou linha dela).
export function FinancialSection({
  indicators,
  referenceMonth,
  financialReturn,
  plantId,
}: {
  indicators: ExecutiveIndicators
  referenceMonth: string
  financialReturn: PlantResource<FinancialReturnResponse>
  plantId: string
}) {
  return (
    <>
      <section className="md:col-span-6 lg:col-span-12">
        <SectionTitle as="h2">Retorno do investimento</SectionTitle>
        {financialReturn.error ? (
          <RetryableError message={financialReturn.error} onRetry={financialReturn.refetch} />
        ) : (
          <div className="max-w-5xl">
            <FinancialReturnSection
              financialReturn={financialReturn.data}
              plantId={plantId}
              onInvestmentRegistered={financialReturn.refetch}
            />
          </div>
        )}
      </section>

      <BillComparisonCard indicators={indicators} referenceMonth={referenceMonth} />
      <SavingsUnavailableCard indicators={indicators} referenceMonth={referenceMonth} />

      <BillDetails indicators={indicators} referenceMonth={referenceMonth} />
    </>
  )
}

// Quando `BillComparisonCard` não aparece (economia sem cálculo, ou backend
// anterior ao ADR-080 sem a conta "sem a usina"), a economia não pode sumir em
// silêncio nem virar R$ 0,00: diz o motivo ou mostra só o valor.
function SavingsUnavailableCard({ indicators, referenceMonth }: { indicators: ExecutiveIndicators; referenceMonth: string }) {
  const savings = toNumber(indicators.estimated_savings_brl)
  const withoutSolar = toNumber(indicators.bill_without_solar_brl ?? null)
  const paid = toNumber(indicators.total_amount_brl)
  if (savings != null && withoutSolar != null && paid != null) return null
  const cycle = formatCycleLabel(referenceMonth)
  // Saldo e cobertura moram na conta do ciclo; sem ela, continuam aqui.
  const balance = toNumber(indicators.credit_balance_kwh)
  const coverage = toNumber(indicators.credit_coverage_rate_percent)
  const imported = toNumber(indicators.imported_kwh)
  return (
    <section className="md:col-span-6 lg:col-span-12" aria-labelledby="savings-fallback-heading">
      <SectionTitle as="h2" id="savings-fallback-heading">
        {`Economia em ${cycle}`}
      </SectionTitle>
      <Card className="sm:p-6">
        {savings == null ? (
          <p className="text-[15px] leading-6 text-[var(--color-text-secondary)]">
            {indicators.savings_unavailable_reason
              ? savingsUnavailableMessage(indicators.savings_unavailable_reason)
              : 'Economia ainda não disponível para este ciclo.'}
          </p>
        ) : (
          <p className="font-display text-[32px] font-semibold tabular-nums text-[var(--color-success-text)]">
            {formatCurrency(savings)}
            <span className="ml-2 align-middle font-sans text-xs font-semibold text-[var(--color-chart-reference)]">Estimado</span>
          </p>
        )}
        {(balance != null || (coverage != null && imported != null && imported > 0)) && (
          <dl className="mt-4 grid grid-cols-1 gap-4 border-t border-[var(--color-border)] pt-4 sm:grid-cols-2">
            {balance != null && (
              <div>
                <dt className="text-[13px] font-medium text-[var(--color-text-secondary)]">Créditos guardados</dt>
                <dd className="mt-0.5 text-[16px] font-semibold tabular-nums text-[var(--color-text-primary)]">{`${formatNumber(balance, 2)} kWh`}</dd>
              </div>
            )}
            {coverage != null && imported != null && imported > 0 && (
              <div>
                <dt className="text-[13px] font-medium text-[var(--color-text-secondary)]">Pago com créditos</dt>
                <dd className="mt-0.5 text-[16px] font-semibold tabular-nums text-[var(--color-text-primary)]">{`${formatNumber(coverage, 1)}% da energia da rede`}</dd>
              </div>
            )}
          </dl>
        )}
      </Card>
    </section>
  )
}

// Decomposição do valor da fatura e as tarifas impressas nela. Recolhido: é
// conferência, não leitura do dia a dia. As duas tarifas eram mostradas lado a
// lado com a tarifa cheia do cálculo "sem a usina" sem explicação, o que parecia
// erro (auditoria de 2026-10-23); aqui cada uma diz o que é.
function BillDetails({ indicators, referenceMonth }: { indicators: ExecutiveIndicators; referenceMonth: string }) {
  const total = toNumber(indicators.total_amount_brl)
  const energy = toNumber(indicators.bill_energy_component_brl)
  const lighting = toNumber(indicators.public_lighting_brl)
  const other = total != null && energy != null && lighting != null ? total - energy - lighting : null
  const billTariffWithTaxes = toNumber(indicators.tariff_with_taxes_brl_kwh)
  const billTariffWithoutTaxes = toNumber(indicators.tariff_without_taxes_brl_kwh)
  const savingsTariff = toNumber(indicators.savings_tariff_brl_kwh ?? null)
  const cycle = formatCycleLabel(referenceMonth)
  // O que a conta "sem a usina" usou, dito pelo próprio motor
  // (`savings_tariff_source`, ADR-080). Sem o campo, nada é afirmado. Não diz
  // de qual linha da fatura veio a tarifa: depende do layout (SCEE ou, antes
  // de dez/2024, "energia ativa fornecida"), que o backend não informa.
  const source = indicators.savings_tariff_source ?? null
  const tariffNote =
    source === 'DISTRIBUTOR_FULL_TARIFF'
      ? savingsTariff != null
        ? `A conta “sem a usina” não usa esta tarifa: usa a tarifa cheia da distribuidora, R$ ${formatNumber(savingsTariff, 3)}/kWh com impostos, que é o que você pagaria sem créditos.`
        : 'A conta “sem a usina” não usa esta tarifa: usa a tarifa cheia da distribuidora, que é o que você pagaria sem créditos.'
      : source === 'BILL_TARIFF'
        ? 'A conta “sem a usina” usa esta tarifa da própria fatura e, por isso, pode subestimar a economia.'
        : null

  if (total == null && billTariffWithTaxes == null) return null

  return (
    <section className="md:col-span-6 lg:col-span-12" aria-label={`Detalhes da fatura de ${cycle}`}>
      <details className="group rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-card)]">
        <summary className="flex min-h-[52px] cursor-pointer list-none items-center justify-between gap-3 rounded-[var(--radius-card)] px-5 text-[15px] font-semibold text-[var(--color-text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] [&::-webkit-details-marker]:hidden">
          {`Detalhes da fatura de ${cycle}`}
          <span aria-hidden="true" className="text-[var(--color-gray-400)] transition-transform duration-150 group-open:rotate-90 motion-reduce:transition-none">
            ›
          </span>
        </summary>
        <div className="flex flex-col gap-5 border-t border-[var(--color-border)] p-5">
          {total != null && energy != null && lighting != null && (
            <div>
              <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">Valor da fatura</p>
              <p className="mt-1 mb-3 font-display text-[24px] font-semibold tabular-nums text-[var(--color-text-primary)]">
                {formatCurrency(total)}
              </p>
              <StackedBar
                segments={[
                  { label: 'Energia e encargos', value: energy, tone: 'neutral' },
                  { label: 'Iluminação pública', value: lighting, color: 'var(--color-energy-consumption)' },
                  ...(other != null && other > 0.005 ? [{ label: 'Outros encargos', value: other, tone: 'danger' as const }] : []),
                ]}
                total={total}
                valueFormatter={formatCurrency}
              />
            </div>
          )}
          {billTariffWithTaxes != null && (
            <div className="grid grid-cols-1 gap-4 border-t border-[var(--color-border)] pt-4 sm:grid-cols-2">
              <dl>
                <dt className="text-[13px] font-medium text-[var(--color-text-secondary)]">Tarifa impressa na fatura</dt>
                <dd className="mt-0.5 text-[16px] font-semibold tabular-nums text-[var(--color-text-primary)]">
                  {`R$ ${formatNumber(billTariffWithTaxes, 3)}/kWh com impostos`}
                </dd>
                {billTariffWithoutTaxes != null && (
                  <dd className="text-xs text-[var(--color-text-secondary)]">{`R$ ${formatNumber(billTariffWithoutTaxes, 3)}/kWh sem impostos`}</dd>
                )}
              </dl>
              {tariffNote && (
                <p className="text-[13px] leading-5 text-[var(--color-text-secondary)] sm:self-center">{tariffNote}</p>
              )}
            </div>
          )}
        </div>
      </details>
    </section>
  )
}
