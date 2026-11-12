// Texto do veredito da conferência de créditos da distribuidora (ADR-084) e
// nome curto da distribuidora. Funções PURAS, movidas sem alteração de
// `components/MonthlyProductionSection.tsx` (que as reexporta) para serem
// usadas também na resposta de "fatura confirmada" sem arrastar o componente
// do gráfico para o chunk de Faturas.
import type { MonthlyProductionCycle } from './monthly-history-contracts'
import { formatCurrency, formatNumber } from '../format'

const DISTRIBUTOR_NAMES: Readonly<Record<string, string>> = {
  EQUATORIAL_GO: 'Equatorial',
}

// Nome curto da distribuidora pelo código da fatura; código desconhecido ou
// ausente vira "distribuidora", nunca um nome inventado.
export function distributorDisplayName(code: string | null | undefined): string {
  return (code && DISTRIBUTOR_NAMES[code]) || 'distribuidora'
}

export function kwh(value: number, digits = 0): string {
  return `${formatNumber(value, digits)} kWh`
}

// Frase única do veredito, com os números que o provam — sempre os do
// próprio `utilityCheck` (medidor e saldo de partida), não os do snapshot.
export function verdictDetail(cycle: MonthlyProductionCycle, distributor: string): string {
  const check = cycle.utilityCheck
  if (!check) return 'Conferência ainda não disponível para este ciclo.'
  switch (check.verdict) {
    case 'LOSS': {
      // Não confirmado: o valor é condicional, nunca dinheiro dado como perdido.
      const value =
        check.missingCreditsValueBrl != null
          ? check.lossConfirmed
            ? ` (cerca de ${formatCurrency(check.missingCreditsValueBrl)} a preços deste ciclo)`
            : ` (se confirmado, cerca de ${formatCurrency(check.missingCreditsValueBrl)} a preços deste ciclo)`
          : ''
      const expired =
        check.expiredCreditsKwh != null && check.expiredCreditsKwh > 0
          ? ` Outros ${kwh(check.expiredCreditsKwh, 2)} venceram pelo prazo de 5 anos, como a fatura anterior avisava.`
          : ''
      if (check.lossConfirmed)
        return `A fatura não mostra ${kwh(check.missingCreditsKwh ?? 0, 2)}${value} nem como abatimento nem como saldo, confirma que 100% da geração é desta unidade e não avisou vencimento do restante. É forte indício de prejuízo: leve a fatura à ouvidoria da ${distributor} e peça a explicação.${expired}`
      return `A fatura não mostra ${kwh(check.missingCreditsKwh ?? 0, 2)}${value} nem como abatimento nem como saldo, e não confirma que 100% da geração é desta unidade. Confira com a ${distributor}: o crédito pode ter ido para outra unidade do rateio.${expired}`
    }
    case 'IMPOSSIBLE':
      return `O medidor da ${distributor} registrou ${kwh(check.meterExportKwh ?? 0)} enviados à rede, mais do que o inversor produziu${cycle.productionKwh != null ? ` (${kwh(cycle.productionKwh)})` : ''}. Um dos dois medidores está errado: vale pedir aferição.`
    case 'SUSPECT':
      return `Só ${formatNumber(check.exportSharePercent ?? 0, 0)}% da produção foi para a rede, contra ${formatNumber(check.exportShareBaselinePercent ?? 0, 0)}% no seu histórico. Pode ser o medidor ou mais consumo durante o dia.`
    case 'OK': {
      const expired =
        check.expiredCreditsKwh != null && check.expiredCreditsKwh > 0
          ? ` ${kwh(check.expiredCreditsKwh, 2)} de crédito venceram (prazo de 5 anos), como a fatura anterior avisava.`
          : ''
      if (check.meterExportKwh != null && check.previousBalanceKwh != null && check.creditsUsedKwh != null && check.creditBalanceKwh != null) {
        return `Todo kWh registrado virou crédito: ${kwh(check.meterExportKwh, 2)} registrados + ${kwh(check.previousBalanceKwh, 2)} de saldo anterior; ${kwh(check.creditsUsedKwh, 2)} usados e saldo de ${kwh(check.creditBalanceKwh, 2)}.${expired}`
      }
      return `Todo kWh registrado virou crédito.${expired}`
    }
    default:
      if (check.reasons.includes('CREDITS_UNBALANCED'))
        return 'Os créditos usados passam do que havia (registrado + saldo anterior). Pode ser crédito vindo de outra unidade ou fatura anterior incorreta: não dá para concluir.'
      if (check.reasons.includes('AMBIGUOUS_PREVIOUS_BILL'))
        return 'Há mais de uma fatura confirmada no mês anterior, com saldos diferentes. Mantenha só a correta para conferir este ciclo.'
      if (check.reasons.includes('NO_METER_READING')) return 'A fatura deste ciclo não traz a leitura do medidor de geração.'
      if (check.reasons.includes('NO_PREVIOUS_BILL')) return 'Falta a fatura do mês anterior para conferir o saldo de créditos.'
      return 'Não há dados suficientes para conferir este ciclo.'
  }
}
