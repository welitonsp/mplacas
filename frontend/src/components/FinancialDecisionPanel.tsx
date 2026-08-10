import type { ExecutiveIndicators, Severity } from '../lib/dashboard/contracts'
import type { FinancialReturnResponse } from '../lib/dashboard/financial-return-contracts'
import {
  isPaybackAlreadyReached,
  paybackUnavailableMessage,
} from '../lib/dashboard/financial-return-contracts'
import { formatCurrency, formatNumber, toNumber } from '../lib/format'
import { SEVERITY_BG, SEVERITY_TEXT } from '../lib/dashboard/visuals'
import { Card } from './Card'

interface FinancialDecision {
  tone: Severity
  title: string
  label: string
  window: string
  owner: string
  summary: string
  primaryAction: string
  evidence: Array<{ label: string; value: string; tone: Severity }>
  playbook: Array<{ title: string; detail: string }>
}

function formatPercent(value: number | null, maximumFractionDigits = 1): string {
  return value === null ? '—' : `${formatNumber(value, maximumFractionDigits)}%`
}

function savingsEvidence(indicators: ExecutiveIndicators): string {
  const estimatedSavings = toNumber(indicators.estimated_savings_brl)
  return estimatedSavings === null ? 'R$ —' : formatCurrency(estimatedSavings)
}

function creditCoverageTone(value: number | null): Severity {
  if (value === null) return 'neutral'
  if (value >= 100) return 'success'
  if (value >= 70) return 'warning'
  return 'danger'
}

export function buildFinancialDecision({
  indicators,
  referenceMonth,
  financialReturn,
  financialReturnError,
}: {
  indicators: ExecutiveIndicators
  referenceMonth: string
  financialReturn: FinancialReturnResponse | null
  financialReturnError: string | null
}): FinancialDecision {
  const estimatedSavings = toNumber(indicators.estimated_savings_brl)
  const creditCoverage = toNumber(indicators.credit_coverage_rate_percent)
  const roi = financialReturn?.unavailable_reason === null ? toNumber(financialReturn.roi_percent) : null
  const paybackReached = financialReturn ? isPaybackAlreadyReached(financialReturn) : false
  const paybackText =
    financialReturn?.payback_projection_months !== null && financialReturn?.payback_projection_months !== undefined
      ? `${financialReturn.payback_projection_months} ciclos`
      : '—'

  const evidence: FinancialDecision['evidence'] = [
    {
      label: 'Economia do ciclo',
      value: savingsEvidence(indicators),
      tone: estimatedSavings === null ? 'warning' : 'success',
    },
    {
      label: 'Cobertura créditos',
      value: formatPercent(creditCoverage),
      tone: creditCoverageTone(creditCoverage),
    },
    {
      label: 'ROI acumulado',
      value: formatPercent(roi),
      tone: roi === null ? 'neutral' : roi >= 100 ? 'success' : 'warning',
    },
    {
      label: 'Payback',
      value: paybackReached ? 'Recuperado' : paybackText,
      tone: paybackReached ? 'success' : financialReturn?.payback_projection_months ? 'warning' : 'neutral',
    },
  ]

  if (financialReturnError) {
    return {
      tone: 'danger',
      title: 'Decisão financeira bloqueada',
      label: 'Erro no retorno',
      window: 'Reprocessar hoje',
      owner: 'Operação + financeiro',
      summary: 'O retorno do investimento não carregou, então ROI e payback não devem ser usados para decisão.',
      primaryAction: 'Tentar novamente e validar se o serviço financeiro voltou antes de apresentar resultado ao cliente.',
      evidence,
      playbook: [
        { title: 'Reprocessar retorno', detail: 'Usar o retry da seção de retorno e confirmar resposta do endpoint financeiro.' },
        { title: 'Preservar ciclo', detail: `Usar apenas custo, créditos e economia do ciclo ${referenceMonth} enquanto ROI não volta.` },
        { title: 'Registrar falha', detail: 'Se persistir, abrir correção técnica com horário, usina e mensagem do erro.' },
      ],
    }
  }

  if (financialReturn === null) {
    return {
      tone: 'neutral',
      title: 'Calculando retorno financeiro',
      label: 'Carregando',
      window: 'Aguardar leitura',
      owner: 'Operação',
      summary: 'A economia do ciclo já pode aparecer, mas ROI e payback ainda estão sendo carregados.',
      primaryAction: 'Aguarde a atualização terminar antes de concluir retorno do investimento.',
      evidence,
      playbook: [
        { title: 'Aguardar retorno', detail: 'Evitar decisão de ROI enquanto o recurso financeiro está carregando.' },
        { title: 'Conferir economia', detail: `Validar se a economia estimada do ciclo ${referenceMonth} está disponível.` },
        { title: 'Reabrir leitura', detail: 'Quando ROI carregar, revisar payback e cobertura de ciclos.' },
      ],
    }
  }

  if (financialReturn.unavailable_reason === 'INVESTMENT_NOT_REGISTERED') {
    return {
      tone: 'warning',
      title: 'ROI bloqueado por CAPEX pendente',
      label: 'Cadastrar investimento',
      window: 'Antes da próxima análise',
      owner: 'Gestão financeira',
      summary: 'A tela já mostra custo e economia do ciclo, mas o retorno do investimento depende do valor investido.',
      primaryAction: 'Cadastrar o CAPEX da usina para liberar ROI acumulado e projeção de payback.',
      evidence,
      playbook: [
        { title: 'Confirmar CAPEX', detail: 'Separar valor investido validado em contrato, nota ou controle financeiro.' },
        { title: 'Cadastrar investimento', detail: 'Usar o formulário de retorno do investimento nesta própria tela.' },
        { title: 'Recalcular decisão', detail: 'Depois do cadastro, revisar ROI, payback e economia acumulada.' },
      ],
    }
  }

  if (financialReturn.unavailable_reason === 'NO_CONSOLIDATED_SAVINGS') {
    return {
      tone: 'warning',
      title: 'Retorno depende de economia consolidada',
      label: 'Aguardar ciclos',
      window: 'Revisar no fechamento',
      owner: 'Financeiro',
      summary: 'Ainda não há ciclo consolidado com economia calculada para sustentar ROI.',
      primaryAction: 'Conferir tarifas e fechamento de relatórios antes de cobrar retorno acumulado.',
      evidence,
      playbook: [
        { title: 'Validar tarifa', detail: 'Garantir que a tarifa do ciclo esteja registrada para estimar economia.' },
        { title: 'Fechar relatório', detail: 'Aguardar ciclos consolidados com economia calculada.' },
        { title: 'Reavaliar ROI', detail: 'Quando houver economia acumulada, revisar ROI e payback.' },
      ],
    }
  }

  if (financialReturn.unavailable_reason === 'INSUFFICIENT_HISTORY') {
    return {
      tone: 'neutral',
      title: 'Histórico financeiro insuficiente',
      label: 'Completar base',
      window: 'Monitorar próximos ciclos',
      owner: 'Financeiro',
      summary: 'O retorno ainda precisa de mais histórico para uma leitura executiva confiável.',
      primaryAction: 'Continuar consolidando ciclos antes de transformar ROI em meta de payback.',
      evidence,
      playbook: [
        { title: 'Manter coleta', detail: 'Preservar relatórios financeiros completos nos próximos ciclos.' },
        { title: 'Evitar promessa', detail: 'Não apresentar payback como data fechada sem histórico suficiente.' },
        { title: 'Revisar cobertura', detail: 'Acompanhar ciclos contados versus ciclos esperados.' },
      ],
    }
  }

  if (paybackReached) {
    return {
      tone: 'success',
      title: 'Investimento recuperado',
      label: 'Payback atingido',
      window: 'Manter rotina mensal',
      owner: 'Gestão financeira',
      summary: 'A economia acumulada já recuperou o valor investido informado.',
      primaryAction: 'Usar a usina como referência de retorno e acompanhar geração de caixa daqui em diante.',
      evidence,
      playbook: [
        { title: 'Registrar marco', detail: 'Marcar o ciclo em que o investimento foi recuperado.' },
        { title: 'Separar ganho futuro', detail: 'Acompanhar economia após payback como geração líquida de caixa.' },
        { title: 'Comparar carteira', detail: 'Usar o desempenho como benchmark para outras usinas.' },
      ],
    }
  }

  if (financialReturn.payback_unavailable_reason !== null) {
    return {
      tone: 'warning',
      title: 'ROI disponível, payback ainda sem base',
      label: 'Payback pendente',
      window: 'Revisar mensalmente',
      owner: 'Financeiro',
      summary: paybackUnavailableMessage(financialReturn.payback_unavailable_reason),
      primaryAction: 'Acompanhar ROI acumulado, mas evitar conclusão de prazo até completar histórico suficiente.',
      evidence,
      playbook: [
        { title: 'Acompanhar ROI', detail: 'Usar o ROI acumulado como sinal de progresso financeiro.' },
        { title: 'Completar histórico', detail: 'Esperar ciclos suficientes com economia média positiva.' },
        { title: 'Reprojetar payback', detail: 'Quando a projeção abrir, revisar premissas com a média recente.' },
      ],
    }
  }

  return {
    tone: 'warning',
    title: 'Retorno em acompanhamento',
    label: 'Payback projetado',
    window: 'Revisar mensalmente',
    owner: 'Gestão financeira',
    summary: `Payback projetado em ${paybackText}, mantida a média recente de economia.`,
    primaryAction: 'Monitorar se a economia mensal sustenta a projeção e agir em tarifa, consumo ou créditos se houver desvio.',
    evidence,
    playbook: [
      { title: 'Comparar economia', detail: 'Verificar se a economia do ciclo acompanha a média usada no payback.' },
      { title: 'Revisar créditos', detail: 'Checar cobertura de créditos e saldo em kWh para evitar perda de benefício.' },
      { title: 'Atualizar projeção', detail: 'Recalcular a leitura executiva após cada fechamento mensal.' },
    ],
  }
}

export function FinancialDecisionPanel({
  indicators,
  referenceMonth,
  financialReturn,
  financialReturnError,
}: {
  indicators: ExecutiveIndicators
  referenceMonth: string
  financialReturn: FinancialReturnResponse | null
  financialReturnError: string | null
}) {
  const decision = buildFinancialDecision({
    indicators,
    referenceMonth,
    financialReturn,
    financialReturnError,
  })

  return (
    <Card accent={decision.tone} className="overflow-hidden">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Decisão financeira</p>
            <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${SEVERITY_BG[decision.tone]} ${SEVERITY_TEXT[decision.tone]}`}>
              {decision.label}
            </span>
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
              {decision.window}
            </span>
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
              {decision.owner}
            </span>
          </div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight text-gray-950">{decision.title}</h2>
          <p className="mt-2 text-sm leading-6 text-gray-600">{decision.summary}</p>
        </div>

        <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-4 lg:min-w-[440px]">
          {decision.evidence.map((item) => (
            <div
              key={item.label}
              className={`rounded-2xl border border-[var(--color-border)] ${SEVERITY_BG[item.tone]} px-3 py-2`}
            >
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{item.label}</p>
              <p className={`mt-1 text-sm font-semibold ${SEVERITY_TEXT[item.tone]}`}>{item.value}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Próxima decisão</p>
          <p className="mt-2 text-sm leading-6 text-gray-700">{decision.primaryAction}</p>
        </div>

        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Plano financeiro</p>
          <ol aria-label="Plano financeiro executivo" className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
            {decision.playbook.map((step, index) => (
              <li key={step.title}>
                <div className="flex items-center gap-2">
                  <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${SEVERITY_BG[decision.tone]} ${SEVERITY_TEXT[decision.tone]}`}>
                    {index + 1}
                  </span>
                  <p className="text-sm font-semibold text-[var(--color-text)]">{step.title}</p>
                </div>
                <p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{step.detail}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Card>
  )
}
