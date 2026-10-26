import { useEffect } from 'react'
import { Link } from 'react-router'
import { fetchExpansionAssessment } from '../lib/api'
import {
  parseExpansionAssessment,
  type ExpansionAssessment,
  type ExpansionMoney,
} from '../lib/dashboard/expansion-contracts'
import { formatCurrency, formatCycleLabel, formatNumber, toNumber } from '../lib/format'
import { usePlantResource } from '../hooks/usePlantResource'
import { DASHBOARD_SETUP_PATH } from '../routes'
import { Card } from './Card'
import { RetryableError } from './RetryableError'
import { SectionTitle } from './SectionTitle'
import { SummaryTile } from './SummaryTile'

// "Vale a pena ampliar a usina?" (ADR-089). Tudo vem pronto do backend; aqui só
// se apresenta. Regras de apresentação (parecer financeiro):
// - "Não vale" tem o mesmo peso visual que "Ampliar" — sem verde de venda;
// - nada de botão de orçamento: o veredito é do motor, não de quem vende;
// - sempre "estimativa", com as premissas à vista.

// Magnitude: o sentido (falta/sobra) vem pronto em `direction`.
const kwh = (value: string | null, digits = 0) => {
  const numeric = toNumber(value)
  return numeric == null ? '—' : `${formatNumber(Math.abs(numeric), digits)} kWh`
}

function period(assessment: ExpansionAssessment): string {
  if (!assessment.firstMonth || !assessment.lastMonth) return 'nos últimos 12 meses'
  return `de ${formatCycleLabel(assessment.firstMonth)} a ${formatCycleLabel(assessment.lastMonth)}`
}

const UNAVAILABLE: Record<string, string> = {
  NOT_ENOUGH_CYCLES: 'Precisamos de 12 faturas confirmadas seguidas, depois do mês em que a usina foi ligada.',
  CYCLES_NOT_CONTIGUOUS: 'Falta fatura de algum mês nos últimos 12. Importe a que falta para fechar o ano.',
  MISSING_METER_OR_CONSUMPTION:
    'Alguma fatura do período não traz a leitura do medidor de geração ou o consumo da rede.',
  SHARE_NOT_CONFIRMED:
    'A fatura não confirma que 100% da geração fica nesta unidade (rateio). Com outras unidades no rateio, a conta teria de somar todas.',
}

const MONEY_UNAVAILABLE: Record<string, string> = {
  FULL_TARIFF_MISSING:
    'O último ciclo não tem a tarifa homologada da ANEEL (ou foi calculado numa versão antiga e precisa ser recalculado em Faturas). Sem ela, não dá para estimar o valor em reais.',
  TRANSITION_ENDED:
    'A transição do Fio B da Lei 14.300 terminou em 2028 e a regra seguinte ainda não foi definida pela ANEEL; o valor em reais fica de fora.',
  WIRE_B_MISSING: 'A fatura não traz o Fio B, então não dá para calcular quanto valeria a energia nova.',
  REGIME_NOT_CONFIRMED:
    'Não foi possível confirmar a regra de cobrança do Fio B da sua usina (data de ligação ausente ou anterior a 2024). O valor em reais fica de fora para não errar.',
  BILL_MODEL_MISMATCH: 'A fatura refeita com as tarifas não fechou com a real; o valor em reais fica de fora.',
}

const WARNINGS: Record<string, string> = {
  SUSPECT_CYCLES:
    'Houve ciclo com queda na parte da produção enviada à rede. Costuma ser mais consumo durante o dia, mas vale conferir em Energia.',
  MINIMUM_BILLING_MAY_APPLY:
    'Em algum mês o consumo da rede ficou baixo; nessa faixa a conta mínima da ligação pode pesar e a ampliação reduz menos.',
  COMMISSIONING_DATE_MISSING: 'Informe o mês em que a usina foi ligada, em Minha usina, para afinar a análise.',
  TARIFF_CLASS_PRESUMED: 'A classe tarifária foi presumida (residencial) no último ciclo.',
}

const INVERTER: Record<string, string> = {
  OK: 'cabe no inversor atual',
  VERIFICAR_DATASHEET: 'fica no limite do inversor atual: confira a potência máxima de placas no manual dele',
  NOVO_INVERSOR: 'passa do limite do inversor atual: precisará de outro inversor',
  MICROINVERSORES: 'com microinversores, a ampliação é feita somando microinversores às placas novas',
  DESCONHECIDO: 'cadastre a potência do inversor para saber se a ampliação cabe nele',
}

function MoneyBlock({ money }: { money: ExpansionMoney | null }) {
  if (money === null) return null
  if (money.unavailableReason !== null) {
    return (
      <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">
        {MONEY_UNAVAILABLE[money.unavailableReason] ?? 'Valor em reais indisponível.'}
      </p>
    )
  }
  const scenario = money.valuesByYear.find((value) => value.scenario)
  return (
    <div className="space-y-2">
      <p className="text-[15px] leading-6 text-[var(--color-text-primary)]">
        Economia estimada de <strong>≈ {formatCurrency(money.monthlySavingFirstYearBrl)} por mês</strong> pela regra
        de {money.valuesByYear[0]?.year ?? money.requestYear}
        {money.valuesByYear.length > 1
          ? `, caindo para ≈ ${formatCurrency(money.monthlySavingScenarioBrl)} por mês a partir de ${
              scenario?.year ?? 2029
            }, porque a energia da parte nova paga uma fatia crescente do Fio B.`
          : ' (cenário com Fio B integral).'}
      </p>
      <table className="w-full max-w-md text-left text-[13px] tabular-nums">
        <caption className="sr-only">Valor de 1 kWh da parte nova, por ano</caption>
        <thead className="text-[var(--color-text-secondary)]">
          <tr>
            <th scope="col" className="py-1 font-medium">Ano</th>
            <th scope="col" className="py-1 font-medium">Fio B pago</th>
            <th scope="col" className="py-1 font-medium">Valor de 1 kWh</th>
          </tr>
        </thead>
        <tbody className="text-[var(--color-text-primary)]">
          {money.valuesByYear.map((value) => (
            <tr key={value.year} className="border-t border-[var(--color-border)]">
              <td className="py-1">
                {value.year}
                {value.scenario ? '+ (cenário)' : ''}
              </td>
              <td className="py-1">{formatNumber((toNumber(value.wireBShare) ?? 0) * 100, 0)}%</td>
              <td className="py-1">{formatCurrency(value.valueBrlKwh)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs leading-5 text-[var(--color-text-secondary)]">
        Pela Lei 14.300, a parte ampliada pedida agora paga 60% do Fio B em 2026, 75% em 2027 e 90% em 2028. De 2029 em
        diante a regra ainda será definida pela ANEEL: usamos Fio B integral como cenário, não como fato. Bandeira
        tarifária fica de fora. Valores a preços do último ciclo, sem reajuste da tarifa.
      </p>
    </div>
  )
}

export function ExpansionContent({ assessment }: { assessment: ExpansionAssessment }) {
  const status = assessment.status
  if (status === 'INDISPONIVEL') {
    return (
      <Card className="sm:p-6">
        <p className="text-[15px] font-semibold text-[var(--color-text-primary)]">Ainda não dá para responder</p>
        <p className="mt-1 text-[13px] leading-5 text-[var(--color-text-secondary)]">
          {UNAVAILABLE[assessment.reasons[0] ?? ''] ?? 'Faltam dados para a análise.'}
          {assessment.reasons[0] === 'NOT_ENOUGH_CYCLES' ? ` Temos ${assessment.cyclesUsed}.` : ''}
        </p>
      </Card>
    )
  }
  if (status === 'CORRIGIR_ANTES') {
    return (
      <Card className="sm:p-6">
        <p className="text-[15px] font-semibold text-[var(--color-text-primary)]">Resolva a usina antes de ampliar</p>
        <p className="mt-1 text-[13px] leading-5 text-[var(--color-text-secondary)]">
          Há ciclo com créditos faltando, envio à rede impossível ou produção muito abaixo do esperado (
          {assessment.problemMonths.map(formatCycleLabel).join(', ')}). Ampliar não resolve defeito nem perda: confira
          esses meses em Energia primeiro.
        </p>
      </Card>
    )
  }

  const warnings = assessment.warnings.map((code) => WARNINGS[code]).filter(Boolean)
  const surplus = status === 'NAO_VALE'
  const balanced = status === 'EQUILIBRADO'
  const headline = surplus
    ? `Não vale ampliar agora: sua usina gera mais do que você consome — sobram em média ${kwh(
        assessment.deficitKwhMonth,
      )} por mês ${period(assessment)}. Ampliar aumentaria a sobra sem reduzir a conta.`
    : balanced
      ? `Geração e consumo estão próximos ${period(assessment)}. Ainda não há falta recorrente que justifique ampliar; reavaliamos a cada fatura.`
      : `Sua usina deixou de cobrir em média ${kwh(assessment.deficitKwhMonth)} por mês do seu consumo ${period(
          assessment,
        )}.`

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <SummaryTile
          label="Consumo da rede no ano"
          value={kwh(assessment.importedKwhTotal)}
          supportingText="Soma das faturas"
          tone="neutral"
        />
        <SummaryTile
          label="Enviado à rede no ano"
          value={kwh(assessment.exportedKwhTotal)}
          supportingText="Medidor da distribuidora"
          tone="neutral"
        />
        <SummaryTile
          label={assessment.direction === 'SOBRA' ? 'Sobra no ano' : assessment.direction === 'ZERO' ? 'Diferença no ano' : 'Falta no ano'}
          value={kwh(assessment.deficitKwhYear)}
          supportingText={`Tolerância: ${kwh(assessment.toleranceKwhYear)}`}
          tone="brand"
        />
        <SummaryTile
          label="Ampliação estimada"
          value={assessment.extraKwp ? `≈ ${formatNumber(assessment.extraKwp, 1)} kWp` : '—'}
          supportingText={
            assessment.extraKwp
              ? `Sobre ${formatNumber(assessment.installedKwp, 2)} kWp de hoje`
              : status === 'AMPLIAR'
                ? 'Faltam dados da usina'
                : 'Não se aplica'
          }
          tone="brand"
        />
      </div>

      <Card className="sm:p-6 space-y-3">
        <p className="text-[15px] font-semibold leading-6 text-[var(--color-text-primary)]">{headline}</p>
        {status === 'AMPLIAR' && (
          <>
            {assessment.balanceBeforeKwh && toNumber(assessment.balanceBeforeKwh)! > 0 && (
              <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">
                O saldo de créditos guardado ({kwh(assessment.balanceBeforeKwh)} no início do período) vinha cobrindo
                essa diferença e terminou em {kwh(assessment.balanceAfterKwh)}.
              </p>
            )}
            {assessment.extraKwp ? (
              <p className="text-[15px] leading-6 text-[var(--color-text-primary)]">
                Uma ampliação de <strong>cerca de {formatNumber(assessment.extraKwp, 1)} kWp</strong> cobriria essa
                falta — {INVERTER[assessment.inverterStatus]}
                {assessment.dcAcRatioAfter ? ` (placas ÷ inversor = ${formatNumber(assessment.dcAcRatioAfter, 2)})` : ''}.
              </p>
            ) : assessment.reasons.includes('INSTALLED_POWER_UNKNOWN') ? (
              <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">
                Para estimar o tamanho da ampliação, informe a potência das placas em{' '}
                <Link to={DASHBOARD_SETUP_PATH} className="font-semibold text-[var(--color-brand-primary)] underline">
                  Minha usina
                </Link>
                .
              </p>
            ) : (
              <p className="text-[13px] leading-5 text-[var(--color-text-secondary)]">
                Faltam meses de produção medida para estimar o tamanho com segurança: temos{' '}
                {assessment.measuredCycles} dos 12 sem dia estimado, e precisamos de pelo menos 10.
              </p>
            )}
            <MoneyBlock money={assessment.money} />
          </>
        )}
        {warnings.length > 0 && (
          <ul
            aria-label="Avisos da análise"
            className="list-disc space-y-1 pl-5 text-[13px] leading-5 text-[var(--color-warning-text)]"
          >
            {warnings.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="sm:p-6">
        <details>
          <summary className="cursor-pointer text-[13px] font-semibold text-[var(--color-text-primary)]">
            Premissas da estimativa
          </summary>
          <ul className="mt-3 space-y-1.5 text-[13px] leading-5 text-[var(--color-text-secondary)]">
            <li>
              Falta = consumo da rede − envio registrado pelo medidor, somados nos 12 ciclos ({period(assessment)}). O
              crédito vale 60 meses, por isso a conta é do ano inteiro, não de um mês.
            </li>
            <li>Diferença de até 5% do consumo da rede no ano conta como equilíbrio.</li>
            {assessment.yieldKwhPerKwpYear && (
              <li>
                Rendimento real da sua usina: {formatNumber(assessment.yieldKwhPerKwpYear, 0)} kWh por kWp ao ano, em{' '}
                {assessment.measuredCycles} meses sem dia estimado. Vale para placas novas com a mesma direção e
                inclinação das atuais; em outra parte do telhado o rendimento muda.
              </li>
            )}
            <li>
              Ampliar exige novo pedido de conexão à distribuidora e pode exigir aumento do padrão de entrada. Acima de
              75 kW a usina deixa de ser microgeração.
            </li>
          </ul>
        </details>
      </Card>

      <p className="text-xs leading-5 text-[var(--color-text-secondary)]">
        Estimativa feita a partir das suas faturas e da produção medida. Não é garantia de economia: tarifas, bandeiras
        e regras do Fio B podem mudar. Compare mais de uma proposta antes de decidir. A conta completa está em “Como calculamos”, no fim da página.
      </p>
    </div>
  )
}

export function ExpansionSection({ plantId, refreshKey = 0 }: { plantId: string; refreshKey?: number }) {
  const resource = usePlantResource({
    plantId,
    fetcher: fetchExpansionAssessment,
    parse: parseExpansionAssessment,
    errorMessage: 'Erro ao buscar a análise de ampliação.',
  })
  // Nova leitura quando a página pede (fatura confirmada, "Atualizar"); a
  // primeira leitura já é do próprio recurso.
  const { refetch } = resource
  useEffect(() => {
    if (refreshKey > 0) refetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])
  return (
    <section className="md:col-span-6 lg:col-span-12" aria-labelledby="expansion-heading">
      <SectionTitle as="h2" id="expansion-heading">
        Vale a pena ampliar a usina?
      </SectionTitle>
      <p className="-mt-1 mb-3 text-[13px] text-[var(--color-text-secondary)]">Estimativa</p>
      {resource.error ? (
        <RetryableError message={resource.error} onRetry={resource.refetch} />
      ) : resource.data === null ? (
        <div className="h-40 animate-pulse rounded-[var(--radius-card)] bg-[var(--color-surface-subtle)]" aria-hidden="true" />
      ) : (
        <ExpansionContent assessment={resource.data} />
      )}
    </section>
  )
}
