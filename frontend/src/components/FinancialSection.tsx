import type { ExecutiveIndicators } from '../lib/dashboard/contracts'
import type { FinancialReturnResponse } from '../lib/dashboard/financial-return-contracts'
import type { PlantResource } from '../hooks/usePlantResource'
import { formatCurrency, toNumber } from '../lib/format'
import { SectionTitle } from './SectionTitle'
import { CurrencyCard } from './CurrencyCard'
import { StackedBar } from './charts/StackedBar'
import { EstimatedSavingsCard } from './EstimatedSavingsCard'
import { FinancialReturnSection } from './FinancialReturnSection'
import { MetricCard } from './MetricCard'
import { RetryableError } from './RetryableError'

// Bloco 3 — "Quanto custou? Qual o retorno?" (Etapa 7 da refatoração de
// `DashboardPage`): dois blocos financeiros que sempre andam juntos (custo do
// ciclo/tarifas/créditos + retorno do investimento), extraídos para um único
// componente por serem os que mais cresceram em `DashboardPage.tsx` (~110
// linhas de JSX) e por dependerem de um subconjunto pequeno e estável de
// dados (`indicators` do ciclo corrente + o recurso `financialReturn`) — sem
// nenhum entrelaçamento com o resto do estado da página. Devolve dois
// `<section>` irmãos (não um só) para preservar exatamente o mesmo layout de
// grade de `DashboardPage` (cada um ocupa uma linha cheia, `md:col-span-6
// lg:col-span-12`) — um `Fragment` não introduz nenhum elemento intermediário
// no DOM, então os dois continuam filhos diretos do grid do jeito que os
// testes de estrutura de grade (`DashboardPage.test.tsx`) já esperam.
export function FinancialSection({
  indicators,
  financialReturn,
  plantId,
}: {
  indicators: ExecutiveIndicators
  financialReturn: PlantResource<FinancialReturnResponse>
  plantId: string
}) {
  // Decomposição da fatura (Parte C): `bill_energy_component_brl` é definido
  // no backend como `total_amount_brl - public_lighting_brl` (clamped em 0,
  // ver intelligence/energy_engine.py::analyze_energy_cycle) — a soma dos
  // dois sempre reconstrói o total, então "resto" existe só para cobrir um
  // eventual encargo futuro não capturado por essas duas categorias, nunca
  // para absorver uma inconsistência de parser. Se qualquer um dos três
  // valores vier `null`, mantém os `CurrencyCard` separados.
  const billTotalAmount = toNumber(indicators.total_amount_brl)
  const billEnergyComponent = toNumber(indicators.bill_energy_component_brl)
  const billPublicLighting = toNumber(indicators.public_lighting_brl)
  const billOtherCharges =
    billTotalAmount != null && billEnergyComponent != null && billPublicLighting != null
      ? billTotalAmount - billEnergyComponent - billPublicLighting
      : null

  return (
    <>
      {/* Valores em R$ (total da fatura, componente de energia, iluminação
          pública, economia estimada), tarifas em R$/kWh e saldo/cobertura de
          créditos — cada card com unidade sempre visível, sem exceção para a
          economia quando a tarifa não está registrada (ver
          EstimatedSavingsCard). */}
      <section className="md:col-span-6 lg:col-span-12">
        <SectionTitle as="h2">Financeiro</SectionTitle>
        {/* Os mesmos oito cards de antes, reagrupados em três subseções
            rotuladas em vez de uma grade achatada — a hierarquia visual
            (fatura vs. tarifa vs. créditos) já existia na cabeça de quem lê,
            só não estava expressa na estrutura (acabamento de hierarquia do
            dashboard). */}
        <div className="space-y-6">
          <div>
            <SectionTitle>Custo do ciclo</SectionTitle>
            {/* Decomposição da fatura (energia + iluminação pública [+
                outros encargos, quando a soma não fecha em cima dos dois
                conhecidos]) — antes eram três `CurrencyCard` soltos sem
                nenhuma indicação visual de que compunham o mesmo total.
                Validado contra o parser real (`bill_energy_component_brl =
                total_amount_brl - public_lighting_brl`, ver
                `intelligence/energy_engine.py`) antes de decompor — ver
                skill `financial-visualization`. */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
              {billTotalAmount != null && billEnergyComponent != null && billPublicLighting != null ? (
                <div className="rounded-lg border border-gray-200 bg-[var(--color-surface)] p-4">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                    Valor total da fatura
                  </p>
                  <p className="mt-1 mb-3 text-2xl font-semibold text-gray-900 tabular-nums">
                    {formatCurrency(billTotalAmount)}
                  </p>
                  <StackedBar
                    segments={[
                      { label: 'Componente energia', value: billEnergyComponent, tone: 'neutral' },
                      { label: 'Iluminação pública', value: billPublicLighting, tone: 'warning' },
                      ...(billOtherCharges != null && billOtherCharges > 0.005
                        ? [{ label: 'Outros encargos', value: billOtherCharges, tone: 'danger' as const }]
                        : []),
                    ]}
                    total={billTotalAmount}
                    valueFormatter={formatCurrency}
                  />
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 lg:col-span-2">
                  <CurrencyCard label="Valor total da fatura" value={indicators.total_amount_brl} />
                  <CurrencyCard
                    label="Componente energia da fatura"
                    value={indicators.bill_energy_component_brl}
                  />
                  <CurrencyCard label="Iluminação pública" value={indicators.public_lighting_brl} />
                </div>
              )}
              <EstimatedSavingsCard
                value={indicators.estimated_savings_brl}
                unavailableReason={indicators.savings_unavailable_reason}
              />
            </div>
          </div>

          <div>
            <SectionTitle>Tarifas</SectionTitle>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <MetricCard
                label="Tarifa com impostos"
                value={indicators.tariff_with_taxes_brl_kwh}
                unit="R$/kWh"
                maximumFractionDigits={6}
              />
              <MetricCard
                label="Tarifa sem impostos"
                value={indicators.tariff_without_taxes_brl_kwh}
                unit="R$/kWh"
                maximumFractionDigits={6}
              />
            </div>
          </div>

          <div>
            <SectionTitle>Créditos de energia</SectionTitle>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <MetricCard label="Saldo de créditos" value={indicators.credit_balance_kwh} unit="kWh" />
              <MetricCard
                label="Cobertura de créditos"
                value={indicators.credit_coverage_rate_percent}
                unit="%"
                barPercent={toNumber(indicators.credit_coverage_rate_percent)}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Retorno do investimento (ADR-067, Etapa E): CAPEX, ROI acumulado e
          projeção de payback, logo depois do custo do ciclo — mesma
          pergunta financeira, num horizonte mais longo. Card único, mais
          estreito que o grid acima (o conteúdo é uma barra de progresso mais
          dois blocos de texto, não uma grade de métricas). */}
      <section className="md:col-span-6 lg:col-span-12">
        <SectionTitle as="h2">Retorno do investimento</SectionTitle>
        {financialReturn.error ? (
          <RetryableError message={financialReturn.error} onRetry={financialReturn.refetch} />
        ) : (
          <div className="max-w-xl">
            <FinancialReturnSection
              financialReturn={financialReturn.data}
              plantId={plantId}
              onInvestmentRegistered={financialReturn.refetch}
            />
          </div>
        )}
      </section>
    </>
  )
}
