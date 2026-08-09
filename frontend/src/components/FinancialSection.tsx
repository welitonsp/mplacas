import type { ExecutiveIndicators } from '../lib/dashboard/contracts'
import type { FinancialReturnResponse } from '../lib/dashboard/financial-return-contracts'
import type { PlantResource } from '../hooks/usePlantResource'
import { formatCurrency, formatNumber, toNumber } from '../lib/format'
import { SectionTitle } from './SectionTitle'
import { CurrencyCard } from './CurrencyCard'
import { StackedBar } from './charts/StackedBar'
import { EstimatedSavingsCard } from './EstimatedSavingsCard'
import { FinancialReturnSection } from './FinancialReturnSection'
import { MetricStrip } from './MetricStrip'
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
  referenceMonth,
  financialReturn,
  plantId,
}: {
  indicators: ExecutiveIndicators
  // `current_cycle.reference_month` do payload executivo (achado F1 da
  // auditoria financeira desta sessão) — exibido junto de "Custo do ciclo",
  // o único bloco deste componente cujo dado é estritamente do ciclo
  // corrente (tarifas variam ~5% entre ciclos, ver ADR-056). "Retorno do
  // investimento" agrega histórico de vários ciclos, por isso não recebe
  // este rótulo. Mesmo padrão textual de `HeroCard.tsx` ("Ciclo de
  // referência: AAAA-MM"), não uma formatação nova.
  referenceMonth: string
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
  const estimatedSavings = toNumber(indicators.estimated_savings_brl)
  const creditCoverage = toNumber(indicators.credit_coverage_rate_percent)
  const roiPercent =
    financialReturn.data?.unavailable_reason === null
      ? toNumber(financialReturn.data.roi_percent)
      : null
  const roiSupportingText =
    financialReturn.status === 'loading'
      ? 'Carregando retorno'
      : financialReturn.error
        ? 'Retorno indisponível'
        : financialReturn.data?.unavailable_reason === 'INVESTMENT_NOT_REGISTERED'
          ? 'Cadastre o CAPEX'
          : 'Acumulado sobre o investimento'

  return (
    <>
      <section className="md:col-span-6 lg:col-span-12">
        <SectionTitle as="h2">Resumo financeiro</SectionTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <FinancialSummaryTile
            label="Economia estimada"
            value={estimatedSavings == null ? 'R$ —' : formatCurrency(estimatedSavings)}
            supportingText={estimatedSavings == null ? 'Tarifa do ciclo ausente' : `Ciclo ${referenceMonth}`}
            tone="solar"
          />
          <FinancialSummaryTile
            label="Cobertura por créditos"
            value={creditCoverage == null ? '—' : `${formatNumber(creditCoverage, 1)}%`}
            supportingText="Quanto do consumo foi coberto"
            tone="grid"
          />
          <FinancialSummaryTile
            label="ROI acumulado"
            value={roiPercent == null ? '—' : `${formatNumber(roiPercent, 1)}%`}
            supportingText={roiSupportingText}
            tone="investment"
          />
        </div>
      </section>

      {/* Valores em R$ (total da fatura, componente de energia, iluminação
          pública, economia estimada), tarifas em R$/kWh e saldo/cobertura de
          créditos — cada card com unidade sempre visível, sem exceção para a
          economia quando a tarifa não está registrada (ver
          EstimatedSavingsCard). */}
      <section className="md:col-span-6 lg:col-span-12">
        {/* Sem heading "Financeiro" isolado aqui (ADR-072, Etapa 6): o módulo
            que hospeda este componente (`pages/dashboard/FinancialPage.tsx`)
            já expõe "Financeiro" como `<h1>` da rota — um segundo heading com
            o mesmo texto logo abaixo seria redundante (mesmo raciocínio já
            aplicado em `OverviewPage`) e ambíguo para `getByText`/leitor de
            tela. As subseções abaixo passam a ser `h2`, direto sob o `h1` do
            módulo (antes eram `h3`, sob o `h2` "Financeiro" removido). */}
        {/* Os mesmos oito cards de antes, agora em dois blocos rotulados —
            "Custo do ciclo" (dinheiro: fatura, tarifas, economia) e
            "Créditos de energia" (energia: saldo/cobertura em kWh) — em vez
            de um único heading "Custo do ciclo" para os oito (estado
            intermediário desta mesma etapa). Achado F3 da auditoria
            financeira desta sessão, já antecipado por
            `docs/UI_UX_AUDIT_2026-08-04.md` (P2-04, "Grandeza fora de
            lugar"): saldo de créditos é kWh, não custo — quem navega por
            heading (leitor de tela) não pode ouvir "Custo do ciclo" e achar
            um valor em kWh como se fosse item de dinheiro. Tarifas (R$/kWh)
            continuam em "Custo do ciclo": são preço, não energia, mantendo o
            mesmo peso visual discreto de linha de apoio de antes (só a
            classificação créditos-vs-custo mudou). Cada bloco usa sua
            própria tira (`MetricStrip`, 2 itens em vez de 4) em vez de voltar
            a 4 `MetricCard` soltos — preserva a compactação visual que
            motivou a tira original, só divide a única tira de 4 colunas em
            duas de 2, uma por grandeza. */}
        <div className="space-y-6">
          <div>
            <SectionTitle as="h2">Custo do ciclo</SectionTitle>
            {/* Ciclo de referência do payload executivo (achado F1 da
                auditoria financeira desta sessão) — sem isso, a tarifa de 6
                casas decimais abaixo (que varia ~5% entre ciclos, ver
                ADR-056) não é rastreável até a fatura confirmada que a
                originou. Mesmo texto/estilo de `HeroCard.tsx`, único outro
                lugar do app que já mostra este dado (lá, só no módulo Visão
                Geral). */}
            <p className="-mt-3 mb-4 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Ciclo de referência: {referenceMonth}
            </p>
            {/* Decomposição da fatura (energia + iluminação pública [+
                outros encargos, quando a soma não fecha em cima dos dois
                conhecidos]) — antes eram três `CurrencyCard` soltos sem
                nenhuma indicação visual de que compunham o mesmo total.
                Validado contra o parser real (`bill_energy_component_brl =
                total_amount_brl - public_lighting_brl`, ver
                `intelligence/energy_engine.py`) antes de decompor — ver
                skill `financial-visualization`. */}
            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)] gap-4 items-stretch">
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

            {/* Tarifas do ciclo (R$/kWh) — mesmos 2 valores de antes
                (`tariff_with_taxes_brl_kwh`/`tariff_without_taxes_brl_kwh`
                com 6 casas decimais, ver ADR-056), numa tira de 2 colunas
                dentro do card de "Custo do ciclo" (linha de apoio da fatura
                acima, não item de destaque próprio). Saldo/cobertura de
                créditos saíram desta tira para o bloco "Créditos de
                energia" abaixo — ver comentário no início desta seção
                (achado F3). */}
            <MetricStrip
              className="mt-4"
              items={[
                {
                  label: 'Tarifa com impostos',
                  value: indicators.tariff_with_taxes_brl_kwh,
                  unit: 'R$/kWh',
                  maximumFractionDigits: 6,
                },
                {
                  label: 'Tarifa sem impostos',
                  value: indicators.tariff_without_taxes_brl_kwh,
                  unit: 'R$/kWh',
                  maximumFractionDigits: 6,
                },
              ]}
            />
          </div>

          <div>
            {/* Bloco próprio para os 2 itens de energia (kWh) que antes
                viviam sob o heading de dinheiro "Custo do ciclo" (achado F3
                da auditoria financeira desta sessão) — mesmos valores/
                unidade/barra de progresso de antes (`credit_balance_kwh`,
                `credit_coverage_rate_percent`), só com heading e
                agrupamento próprios, para que um leitor de tela não ouça
                "Custo do ciclo" e encontre um saldo em kWh como se fosse
                item de dinheiro. */}
            <SectionTitle as="h2">Créditos de energia</SectionTitle>
            <MetricStrip
              items={[
                { label: 'Saldo de créditos', value: indicators.credit_balance_kwh, unit: 'kWh' },
                {
                  label: 'Cobertura de créditos',
                  value: indicators.credit_coverage_rate_percent,
                  unit: '%',
                  barPercent: toNumber(indicators.credit_coverage_rate_percent),
                },
              ]}
            />
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
          <div className="max-w-5xl">
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

function FinancialSummaryTile({
  label,
  value,
  supportingText,
  tone,
}: {
  label: string
  value: string
  supportingText: string
  tone: 'solar' | 'grid' | 'investment'
}) {
  const toneClass =
    tone === 'solar'
      ? 'bg-[var(--color-energy-solar)]'
      : tone === 'grid'
        ? 'bg-[var(--color-energy-grid)]'
        : 'bg-[var(--color-energy-consumption)]'

  return (
    <div className="min-h-[7.5rem] rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 shadow-sm sm:min-h-[8.5rem] sm:p-4">
      <div className={`mb-3 h-1.5 w-12 rounded-sm sm:mb-4 ${toneClass}`} />
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-2 text-xl font-semibold text-gray-900 tabular-nums sm:text-2xl">{value}</p>
      <p className="mt-1 text-xs text-gray-500">{supportingText}</p>
    </div>
  )
}
