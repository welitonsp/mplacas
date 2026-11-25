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
          description="O retorno usa a economia real das faturas confirmadas a partir do mês seguinte à ligação (a do mês da ligação é de geração parcial). Importe a fatura em PDF na seção Faturas de energia, no fim desta página."
          tone="brand"
          action={<GoToBillsButton />}
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

// As faturas ficam no FIM da aba Dinheiro (`#faturas`, `FinancialPage`). O
// roteador não rola até a âncora estando na mesma página, então o botão rola e
// leva o foco ao botão de importar, para teclado e leitor de tela chegarem lá.
function GoToBillsButton() {
  return (
    <button
      type="button"
      onClick={() => {
        document.getElementById('faturas')?.scrollIntoView?.({ block: 'start' })
        document.getElementById('bill-import-button')?.focus({ preventScroll: true })
      }}
      className="inline-flex min-h-[44px] items-center rounded-lg bg-[var(--color-brand-primary)] px-4 text-sm font-semibold text-[var(--color-on-brand)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2"
    >
      Ir para as faturas
    </button>
  )
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

// Pontos percentuais (valor absoluto) a partir de uma fração já calculada no backend.
function pointsOf(fraction: number): string {
  return formatNumber(Math.abs(fraction) * 100, 1)
}

function replacementYears(years: number[]): string {
  return years.length <= 1 ? `no ano ${years[0] ?? '—'}` : `nos anos ${years.join(' e ')}`
}

function InvestorPanelContent({ panel }: { panel: InvestorPanel }) {
  const projection = panel.projection!
  const premises = panel.premises
  const irr = toNumber(projection.irrPerYear)
  // Diferença TIR − CDI líquido vem pronta do backend (ADR-012).
  const spread = toNumber(projection.irrSpreadOverCdiPerYear)
  const npv = toNumber(projection.npvAtCdiNetBrl)
  const beatsCdi = npv != null && npv > 0
  const annualReturn = toNumber(projection.annualSavingOverInvestment)
  const baselineCycles = projection.baselineCycles ?? panel.cyclesCounted

  const spreadText =
    spread == null
      ? null
      : `${pointsOf(spread)} pontos ${spread >= 0 ? 'acima' : 'abaixo'} do CDI líquido de IR (${percent(projection.cdiNetPerYear)})`
  const npvText =
    npv == null
      ? null
      : `Vale ${formatCurrency(Math.abs(npv))} ${beatsCdi ? 'a mais' : 'a menos'} que o CDI, trazido a valor presente pelo próprio CDI.`
  const verdict =
    irr == null
      ? 'Nas premissas atuais, a economia não chega a pagar o investimento no horizonte de 25 anos.'
      : `Projeção: a usina rende ${percent(projection.irrPerYear)} ao ano${spreadText ? `, ${spreadText}` : ''}.${npvText ? ` ${npvText}` : ''}`

  // Série em dinheiro de hoje (deflacionada no backend pelo IPCA da premissa).
  // Sem ela (backend antigo) o gráfico some: nunca zero, nunca o nominal sem rótulo.
  const realPoints = projection.patrimony.map((point) => ({
    year: point.year,
    cdi: toNumber(point.cdiPathRealBrl),
    solar: toNumber(point.solarPathRealBrl),
  }))
  const chartPoints = realPoints.every((point) => point.cdi != null && point.solar != null)
    ? realPoints.map((point) => ({ year: point.year, cdi: point.cdi as number, solar: point.solar as number }))
    : null
  const horizonYears = premises?.horizonYears ?? chartPoints?.[chartPoints.length - 1]?.year ?? null
  const lastNominal = projection.patrimony[projection.patrimony.length - 1]

  const realized = panel.realized
  const coverage = realized ? realized.cyclesCounted / Math.max(1, realized.monthsElapsed) : 0
  const missingCycles = realized ? Math.max(0, realized.monthsElapsed - realized.cyclesCounted) : 0

  // Avisos que mudam a leitura dos números ficam ACIMA deles, visíveis — não
  // escondidos nas premissas (estimado nunca se apresenta como confirmado).
  const cautions: string[] = []
  if (panel.lowConfidenceBaseline) {
    cautions.push(
      `A projeção parte de ${baselineCycles} ${baselineCycles === 1 ? 'fatura confirmada' : 'faturas confirmadas'}: ainda não cobre as estações do ano e pode mudar bastante. Fica firme com 12 meses de faturas.`,
    )
  }
  if (panel.preInjectionFix) {
    cautions.push(
      'Parte das faturas foi calculada por uma versão anterior do cálculo (antes da correção da energia injetada e da tarifa cheia) e tende a subestimar a economia.',
    )
  }
  if (panel.billTariffFloor) {
    cautions.push(
      'Em parte das faturas não há tarifa homologada cadastrada para o ciclo: a economia usa o preço da própria fatura e é um valor mínimo (piso), podendo ser maior na realidade.',
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
          {/* Um aviso só vira parágrafo; lista com marcador só quando há mais
              de um (antes: lista de um item com bolinha solta). */}
          {cautions.length === 1 ? (
            <p className="mt-1">{cautions[0]}</p>
          ) : (
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {cautions.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Leitura simples do que JÁ aconteceu (economia das faturas ÷ valor
          investido): é realizado, não projeção, e por isso fica fora do grupo
          "Projeção". Com menos de 12 meses é uma média anualizada. */}
      {annualReturn != null && (
        <div className="space-y-1 rounded-[var(--radius-card)] border border-[var(--color-border)] p-3 sm:p-4">
          <span className="inline-flex rounded-full border border-[var(--color-success-text)] px-3 py-0.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-success-text)]">
            Realizado
          </span>
          <p className="text-base font-semibold leading-6 text-[var(--color-text-primary)]">
            {`A usina devolve cerca de ${formatNumber(annualReturn * 100, 0)}% do investimento por ano`}
          </p>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {baselineCycles >= 12
              ? 'Economia dos últimos 12 meses de faturas confirmadas, em relação ao valor investido.'
              : `Média anualizada: economia ${baselineCycles === 1 ? 'do último mês' : `dos últimos ${baselineCycles} meses`} de faturas confirmadas, projetada para 12 meses, em relação ao valor investido.`}
          </p>
        </div>
      )}

      {/* Selo de projeção: SEMPRE presente, com ou sem poucas faturas. O bloco
          abaixo é uma estimativa com premissas, não resultado já obtido (o
          realizado vem mais adiante, separado). */}
      <div
        role="group"
        aria-label="Projeção"
        className="space-y-4 rounded-[var(--radius-card)] border border-dashed border-[var(--color-border)] p-3 sm:p-4"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-[var(--color-brand-primary)] px-3 py-0.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-brand-primary)]">
            Projeção
          </span>
          <span className="text-[13px] text-[var(--color-text-secondary)]">
            Estimativa com premissas, não é resultado já obtido.
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
          <SummaryTile
            label="Projeção: retorno anual (TIR)"
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
            label="Diferença para o CDI (VPL)"
            value={npv == null ? '—' : formatCurrency(Math.abs(npv))}
            supportingText={`${beatsCdi ? 'a mais' : 'a menos'} que o CDI, trazido a valor presente pelo próprio CDI`}
            tone={beatsCdi ? 'success' : 'warning'}
          />
          <SummaryTile
            label="Tempo para se pagar"
            value={months(projection.paybackSimpleMonths)}
            supportingText={`Projeção com manutenção e inversor. Contando o CDI: ${months(projection.paybackDiscountedMonths)}`}
            tone="neutral"
          />
        </div>

        {premises && (
          <p className="text-xs leading-5 text-[var(--color-text-secondary)]">
            {`Premissas: CDI ${percent(premises.cdiPerYear)} a.a. · inflação ${percent(premises.ipcaPerYear)} a.a. · placas perdem ${percent(premises.degradationPerYear)} a.a. · Fio B ${
              projection.wireBApplied ? 'subindo até 100% em 2029' : 'não aplicado'
            } · inversor trocado ${replacementYears(premises.inverterReplacementYears)} (${percent(premises.inverterReplacementFraction, 0)} do investimento) · manutenção ${percent(premises.omPerYearFraction)} do investimento ao ano.`}
          </p>
        )}

        <Card className="sm:p-6">
          <p className="text-sm font-semibold leading-6 text-[var(--color-text-primary)]">{verdict}</p>
          <p className="mt-1 text-[13px] text-[var(--color-text-secondary)]">
            Patrimônio nos dois caminhos: a usina com cada economia aplicada no CDI, e o mesmo investimento só no CDI.
          </p>
          {premises && horizonYears != null && (
            <p className="mt-1 text-[13px] text-[var(--color-text-secondary)]">
              {`Em dinheiro de hoje (corrigido pela inflação de ${percent(premises.ipcaPerYear)} a.a.).`}
            </p>
          )}
          {premises && horizonYears != null && (
            <p className="mt-1 text-[13px] font-medium text-[var(--color-text-primary)]">
              {`Supõe aplicar toda a economia no CDI de ${percent(premises.cdiPerYear)} a.a. por ${horizonYears} anos.`}
            </p>
          )}
          <div className="mt-4">
            {chartPoints == null ? (
              <p className="text-sm text-[var(--color-text-secondary)]">
                A evolução do patrimônio em dinheiro de hoje não está disponível agora.
              </p>
            ) : (
              <PatrimonyLines
                points={chartPoints}
                crossover={projection.paybackDiscountedMonths == null ? null : projection.paybackDiscountedMonths / 12}
                ariaLabel={`Patrimônio em ${horizonYears ?? chartPoints[chartPoints.length - 1].year} anos, em dinheiro de hoje: usina com economias no CDI contra o investimento só no CDI`}
              />
            )}
          </div>
        </Card>
      </div>

      {/* Uma coluna: lado a lado, "Premissas" (fechado) ficava como um cartão
          órfão de meia largura ao lado do realizado. */}
      <div className="grid grid-cols-1 gap-4">
        <Card className="sm:p-6">
          <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">
            Realizado desde a ligação{panel.commissionedMonth ? ` (${formatCycleLabel(panel.commissionedMonth)})` : ''}
          </p>
          {realized == null ? (
            <p className="mt-2 text-sm text-[var(--color-text-primary)]">Sem CDI suficiente para comparar o período.</p>
          ) : coverage < MIN_REALIZED_COVERAGE ? (
            <>
              <p className="mt-2 text-sm font-semibold text-[var(--color-text-primary)]">
                {formatCurrency(realized.accumulatedSavingsBrl)} de economia calculada a partir das faturas confirmadas, em {realized.cyclesCounted}{' '}
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
                <dd className="font-display text-lg font-semibold tabular-nums text-[var(--color-text-primary)]">
                  {formatCurrency(realized.solarPathNetBrl)}
                </dd>
              </div>
              <div>
                <dt className="text-[13px] text-[var(--color-text-secondary)]">Investimento só no CDI</dt>
                <dd className="font-display text-lg font-semibold tabular-nums text-[var(--color-text-primary)]">
                  {formatCurrency(realized.cdiPathNetBrl)}
                </dd>
              </div>
              <p className="col-span-2 text-xs leading-5 text-[var(--color-text-secondary)]">
                Líquidos de IR, até {formatCycleLabel(realized.asOfMonth)}, último mês com CDI publicado: faturas
                de meses seguintes entram quando o CDI do mês for divulgado. O caminho da usina não inclui o valor
                da própria usina, que continua gerando.
              </p>
            </dl>
          )}
        </Card>

        <Card className="sm:p-6">
          <details>
            <summary className="flex min-h-[44px] cursor-pointer items-center text-[13px] font-semibold text-[var(--color-text-primary)]">
              Premissas da projeção
            </summary>
            {panel.premises && (
              <ul className="mt-3 space-y-1.5 text-[13px] leading-5 text-[var(--color-text-secondary)]">
                <li>
                  Economia de partida: {formatCurrency(projection.baselineMonthlySavingsBrl)}/mês, média d{baselineCycles === 1 ? 'o' : 'os'}
                  {baselineCycles === 1 ? ' último mês' : ` últimos ${baselineCycles} meses`} de faturas confirmadas
                  posteriores à ligação (no máximo 12), ajustada à parcela do Fio B do ano da última fatura.
                  Meses usados: {baselineCycles} de {panel.cyclesCounted} {panel.cyclesCounted === 1 ? 'fatura' : 'faturas'}.
                </li>
                <li>Tarifa reajustada pelo IPCA de 12 meses: {percent(panel.premises.tariffGrowthPerYear)} ao ano.</li>
                <li>Perda de rendimento das placas: {percent(panel.premises.degradationPerYear)} ao ano.</li>
                <li>
                  Premissas de custo conservadoras: manutenção de {percent(panel.premises.omPerYearFraction)} do
                  investimento ao ano e troca do inversor {replacementYears(panel.premises.inverterReplacementYears)},
                  cada uma a {percent(panel.premises.inverterReplacementFraction, 0)} do investimento em dinheiro de hoje
                  (corrigida pelo IPCA até o ano da troca).
                </li>
                <li>
                  Os valores do gráfico estão em dinheiro de hoje: o patrimônio de cada ano é dividido pela inflação
                  acumulada ({percent(panel.premises.ipcaPerYear)} ao ano).
                  {lastNominal?.solarPathBrl != null &&
                    ` Em valores nominais (sem descontar a inflação), em ${panel.premises.horizonYears} anos: usina ${formatCurrency(lastNominal.solarPathBrl)} contra ${formatCurrency(lastNominal.cdiPathBrl)} só no CDI.`}
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
