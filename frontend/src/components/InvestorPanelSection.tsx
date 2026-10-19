import { Link } from 'react-router'
import type { InvestorPanel } from '../lib/dashboard/investor-contracts'
import { formatCurrency, formatCycleLabel, formatNumber, toNumber } from '../lib/format'
import { DASHBOARD_SETUP_PATH } from '../routes'
import { Card } from './Card'
import { EmptyState } from './EmptyState'
import { RetryableError } from './RetryableError'
import { SectionTitle } from './SectionTitle'
import { SummaryTile } from './SummaryTile'
import { PatrimonyLines } from './charts/PatrimonyLines'

// Painel do investidor (ADR-079). A pergunta: "a usina rende mais que deixar o
// dinheiro no CDI?". A régua é o CDB a 100% do CDI LÍQUIDO de IR, porque a
// economia da usina não paga imposto e o rendimento do CDI paga. Todos os
// números vêm prontos do backend; aqui só se apresenta, separando o que é
// REALIZADO (faturas confirmadas + CDI efetivo) do que é PROJEÇÃO (premissas).

// Abaixo desta cobertura (faturas confirmadas / meses desde a ligação), a
// comparação realizada mente por omissão — mostra-se a falta, não o placar.
const MIN_REALIZED_COVERAGE = 0.8

function percent(fraction: string | null | undefined, digits = 1): string {
  const value = toNumber(fraction ?? null)
  return value == null ? '—' : `${formatNumber(value * 100, digits)}%`
}

function months(count: number | null): string {
  if (count == null) return 'Não se paga no horizonte'
  const years = Math.floor(count / 12)
  const rest = count % 12
  const parts = []
  if (years > 0) parts.push(`${years} ${years === 1 ? 'ano' : 'anos'}`)
  if (rest > 0) parts.push(`${rest} ${rest === 1 ? 'mês' : 'meses'}`)
  return parts.join(' e ') || '0 meses'
}

function UnavailableState({ panel }: { panel: InvestorPanel }) {
  switch (panel.unavailableReason) {
    case 'INVESTMENT_NOT_REGISTERED':
    case 'COMMISSIONING_DATE_MISSING':
      return (
        <EmptyState
          title={
            panel.unavailableReason === 'INVESTMENT_NOT_REGISTERED'
              ? 'Informe o valor investido'
              : 'Informe o mês em que a usina foi ligada'
          }
          description="Sem esse dado não há como comparar a usina com o CDI. Leva um minuto."
          tone="brand"
          action={
            <Link
              to={DASHBOARD_SETUP_PATH}
              className="inline-flex min-h-[44px] items-center rounded-lg bg-[var(--color-brand-primary)] px-4 text-sm font-semibold text-[var(--color-on-brand)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2"
            >
              Ir para Minha usina
            </Link>
          }
        />
      )
    case 'NO_CONSOLIDATED_SAVINGS':
      return (
        <EmptyState
          title="Confirme a primeira fatura"
          description="O retorno usa a economia real das faturas confirmadas a partir do mês seguinte à ligação (a do mês da ligação é de geração parcial). Importe a fatura em PDF no topo desta página."
          tone="brand"
        />
      )
    default:
      return (
        <EmptyState
          title="Indicadores do Banco Central indisponíveis"
          description="Não foi possível obter o CDI e o IPCA agora. A comparação volta assim que os dados forem atualizados."
          tone="neutral"
        />
      )
  }
}

export function InvestorPanelSection({
  panel,
  error,
  onRetry,
}: {
  panel: InvestorPanel | null
  error: string | null
  onRetry: () => void
}) {
  return (
    <section className="md:col-span-6 lg:col-span-12" aria-labelledby="investor-heading">
      <SectionTitle as="h2" id="investor-heading">
        Usina × CDI: vale mais que o investimento?
      </SectionTitle>
      {error ? (
        <RetryableError message={error} onRetry={onRetry} />
      ) : panel === null ? (
        <div className="h-40 animate-pulse rounded-[var(--radius-card)] bg-[var(--color-surface-subtle)]" aria-hidden="true" />
      ) : panel.unavailableReason !== null || panel.projection === null ? (
        <UnavailableState panel={panel} />
      ) : (
        <InvestorPanelContent panel={panel} />
      )}
    </section>
  )
}

function InvestorPanelContent({ panel }: { panel: InvestorPanel }) {
  const projection = panel.projection!
  const irr = toNumber(projection.irrPerYear)
  const cdiNet = toNumber(projection.cdiNetPerYear)
  const spreadPoints = irr != null && cdiNet != null ? (irr - cdiNet) * 100 : null
  const npv = toNumber(projection.npvAtCdiNetBrl)
  const beatsCdi = npv != null && npv > 0

  const verdict =
    irr == null
      ? 'Nas premissas atuais, a economia não chega a pagar o investimento no horizonte de 25 anos.'
      : `Projeção: a usina rende ${percent(projection.irrPerYear)} ao ano, ${formatNumber(Math.abs(spreadPoints ?? 0), 1)} pontos ${
          (spreadPoints ?? 0) >= 0 ? 'acima' : 'abaixo'
        } do CDI líquido de IR (${percent(projection.cdiNetPerYear)}). Em dinheiro de hoje, vale ${formatCurrency(
          Math.abs(npv ?? 0),
        )} ${beatsCdi ? 'a mais' : 'a menos'} do que ter deixado o investimento no CDI.`

  const points = projection.patrimony.map((point) => ({
    year: point.year,
    cdi: toNumber(point.cdiPathBrl) ?? 0,
    solar: toNumber(point.solarPathBrl) ?? 0,
  }))

  const realized = panel.realized
  const coverage = realized ? realized.cyclesCounted / Math.max(1, realized.monthsElapsed) : 0
  const missingCycles = realized ? Math.max(0, realized.monthsElapsed - realized.cyclesCounted) : 0

  // Avisos que mudam a leitura dos números ficam ACIMA deles, visíveis — não
  // escondidos nas premissas (estimado nunca se apresenta como confirmado).
  const cautions: string[] = []
  if (panel.lowConfidenceBaseline) {
    cautions.push(
      `A projeção parte de ${panel.cyclesCounted} ${panel.cyclesCounted === 1 ? 'fatura confirmada' : 'faturas confirmadas'}: ainda não cobre as estações do ano e pode mudar bastante. Fica firme com 12 meses de faturas.`,
    )
  }
  if (panel.includesPreCorrectionCycles) {
    cautions.push(
      'Parte das faturas foi calculada antes da correção da energia injetada e pode superestimar a economia em cerca de R$ 11 por mês.',
    )
  }

  return (
    <div className="space-y-4">
      {cautions.length > 0 && (
        <div
          role="note"
          aria-label="Avisos sobre a projeção"
          className="rounded-[var(--radius-card)] border border-[var(--color-warning)]/40 bg-[var(--color-warning-light)] px-4 py-3 text-[13px] leading-5 text-[var(--color-warning-text)]"
        >
          <p className="font-semibold">Estimativa preliminar</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {cautions.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <SummaryTile
          label="Rendimento da usina (TIR)"
          value={irr == null ? '—' : `${percent(projection.irrPerYear)} a.a.`}
          supportingText={`Real: ${percent(projection.irrRealPerYear)} a.a. acima da inflação`}
          tone={beatsCdi ? 'success' : 'warning'}
        />
        <SummaryTile
          label="CDI líquido de IR"
          value={`${percent(projection.cdiNetPerYear)} a.a.`}
          supportingText={`CDI 12 meses ${percent(panel.indices.cdi12mPerYear)}, IR no resgate`}
          tone="neutral"
        />
        <SummaryTile
          label="Ganho sobre o CDI (VPL)"
          value={npv == null ? '—' : formatCurrency(npv)}
          supportingText="Em dinheiro de hoje"
          tone={beatsCdi ? 'success' : 'warning'}
        />
        <SummaryTile
          label="Tempo para se pagar"
          value={months(projection.paybackSimpleMonths)}
          supportingText={`Contando o CDI: ${months(projection.paybackDiscountedMonths)}`}
          tone="neutral"
        />
      </div>

      <Card className="sm:p-6">
        <p className="text-[15px] font-semibold leading-6 text-[var(--color-text-primary)]">{verdict}</p>
        <p className="mt-1 text-[13px] text-[var(--color-text-secondary)]">
          Patrimônio nos dois caminhos: a usina com cada economia aplicada no CDI, e o mesmo investimento só no CDI.
        </p>
        <div className="mt-4">
          <PatrimonyLines
            points={points}
            crossover={projection.paybackDiscountedMonths == null ? null : projection.paybackDiscountedMonths / 12}
            ariaLabel={`Patrimônio em ${points[points.length - 1]?.year ?? 0} anos: usina com economias no CDI contra o investimento só no CDI`}
          />
        </div>
      </Card>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <Card className="sm:p-6">
          <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">
            Realizado desde a ligação{panel.commissionedMonth ? ` (${formatCycleLabel(panel.commissionedMonth)})` : ''}
          </p>
          {realized == null ? (
            <p className="mt-2 text-sm text-[var(--color-text-primary)]">Sem CDI suficiente para comparar o período.</p>
          ) : coverage < MIN_REALIZED_COVERAGE ? (
            <>
              <p className="mt-2 text-[15px] font-semibold text-[var(--color-text-primary)]">
                {formatCurrency(realized.accumulatedSavingsBrl)} de economia confirmada em {realized.cyclesCounted}{' '}
                {realized.cyclesCounted === 1 ? 'fatura' : 'faturas'}
              </p>
              <p className="mt-1 text-[13px] leading-5 text-[var(--color-warning-text)]">
                Faltam faturas de {missingCycles} {missingCycles === 1 ? 'mês' : 'meses'} desde a ligação. Importe-as para
                comparar o realizado com o CDI; até lá, a comparação acima é uma projeção.
              </p>
            </>
          ) : (
            <dl className="mt-3 grid grid-cols-2 gap-4">
              <div>
                <dt className="text-[13px] text-[var(--color-text-secondary)]">Economias aplicadas no CDI</dt>
                <dd className="font-display text-[20px] font-semibold tabular-nums text-[var(--color-text-primary)]">
                  {formatCurrency(realized.solarPathNetBrl)}
                </dd>
              </div>
              <div>
                <dt className="text-[13px] text-[var(--color-text-secondary)]">Investimento só no CDI</dt>
                <dd className="font-display text-[20px] font-semibold tabular-nums text-[var(--color-text-primary)]">
                  {formatCurrency(realized.cdiPathNetBrl)}
                </dd>
              </div>
              <p className="col-span-2 text-xs leading-5 text-[var(--color-text-secondary)]">
                Líquidos de IR, até {formatCycleLabel(realized.asOfMonth)}. O caminho da usina não inclui o valor da
                própria usina, que continua gerando.
              </p>
            </dl>
          )}
        </Card>

        <Card className="sm:p-6">
          <details>
            <summary className="cursor-pointer text-[13px] font-semibold text-[var(--color-text-primary)]">
              Premissas da projeção
            </summary>
            {panel.premises && (
              <ul className="mt-3 space-y-1.5 text-[13px] leading-5 text-[var(--color-text-secondary)]">
                <li>
                  Economia de partida: {formatCurrency(projection.baselineMonthlySavingsBrl)}/mês, média de{' '}
                  {panel.cyclesCounted} {panel.cyclesCounted === 1 ? 'fatura' : 'faturas'} confirmadas
                  posteriores à ligação.
                </li>
                <li>Tarifa reajustada pelo IPCA de 12 meses: {percent(panel.premises.tariffGrowthPerYear)} ao ano.</li>
                <li>Perda de rendimento das placas: {percent(panel.premises.degradationPerYear)} ao ano.</li>
                <li>
                  Manutenção: {percent(panel.premises.omPerYearFraction)} do investimento ao ano; troca do inversor no ano{' '}
                  {panel.premises.inverterReplacementYear} ({percent(panel.premises.inverterReplacementFraction, 0)} do
                  investimento).
                </li>
                <li>
                  Fio B (Lei 14.300):{' '}
                  {projection.wireBApplied
                    ? '75% em 2027, 90% em 2028 e integral a partir de 2029 (regra ainda sem regulamentação). Enquadramento estimado pela data de ligação; a lei usa a data do pedido de conexão.'
                    : 'não aplicado (ligação antes de 07/01/2023 ou fatura sem a tarifa do Fio B). Enquadramento estimado pela data de ligação; a lei usa a data do pedido de conexão.'}
                </li>
                <li>
                  CDI futuro igual ao dos últimos 12 meses ({percent(panel.premises.cdiPerYear)}), num CDB mantido até
                  o resgate, com IR regressivo sobre o ganho ({percent(panel.premises.longTermIncomeTax, 0)} acima de 2
                  anos). Equivale a {percent(projection.cdiNetPerYear)} ao ano líquidos em{' '}
                  {panel.premises.horizonYears} anos.
                </li>
                <li>
                  Fonte dos índices: {panel.indices.source}
                  {panel.indices.asOfMonth ? `, até ${formatCycleLabel(panel.indices.asOfMonth)}` : ''}.
                </li>
              </ul>
            )}
          </details>
        </Card>
      </div>
    </div>
  )
}
