import type { FinancialReturnResponse } from '../lib/dashboard/financial-return-contracts'
import {
  coverageLabel,
  financialReturnUnavailableMessage,
  isPaybackAlreadyReached,
  paybackUnavailableMessage,
} from '../lib/dashboard/financial-return-contracts'
import { clampPercent, formatCurrency, formatNumber, toNumber } from '../lib/format'
import { Card } from './Card'
import { CapexRegistrationForm } from './CapexRegistrationForm'

// Seção "Retorno do investimento" (ADR-067, Decisão item 7). `financialReturn ===
// null` é o estado de carregamento; a partir daí, três formas de indisponibilidade
// e o estado com dados, cada um com sua própria mensagem/ação — nunca um card vazio
// silencioso nem um "R$ 0,00"/"0%" fabricado quando o backend manda `null`.
export function FinancialReturnSection({
  financialReturn,
  plantId,
  onInvestmentRegistered,
}: {
  financialReturn: FinancialReturnResponse | null
  plantId: string
  onInvestmentRegistered: () => void
}) {
  if (financialReturn === null) {
    return (
      <Card className="animate-pulse">
        <div className="h-3 w-1/3 rounded bg-gray-200" />
        <div className="mt-4 h-8 w-1/2 rounded bg-gray-100" />
      </Card>
    )
  }

  // Sem CAPEX cadastrado: nenhum campo derivado existe (todos `null` por contrato),
  // e é aqui que o diálogo de cadastro do CAPEX vive — não em uma área de
  // configurações nova (ADR-067, Decisão item 7).
  if (financialReturn.unavailable_reason === 'INVESTMENT_NOT_REGISTERED') {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Retorno do investimento</p>
        <p className="mt-4 text-sm text-gray-500">
          {financialReturnUnavailableMessage('INVESTMENT_NOT_REGISTERED')}
        </p>
        <CapexRegistrationForm plantId={plantId} onSuccess={onInvestmentRegistered} />
      </Card>
    )
  }

  if (financialReturn.unavailable_reason !== null) {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Retorno do investimento</p>
        <p className="mt-4 text-sm text-gray-500">
          {financialReturnUnavailableMessage(financialReturn.unavailable_reason)}
        </p>
      </Card>
    )
  }

  // ROI disponível a partir daqui — `payback_unavailable_reason` ainda pode ser
  // não-nulo mesmo com ROI válido (ver ADR-067, Decisão item 5).
  const roiPercent = toNumber(financialReturn.roi_percent)
  const barPercent = clampPercent(roiPercent ?? 0)
  const coverage = coverageLabel(financialReturn)
  const paybackReached = isPaybackAlreadyReached(financialReturn)
  const paybackLabel = paybackReached
    ? 'Recuperado'
    : financialReturn.payback_projection_months !== null
      ? `${financialReturn.payback_projection_months} ciclos`
      : 'Em cálculo'
  const paybackSupportingText = paybackReached
    ? 'Investimento já recuperado'
    : financialReturn.payback_projection_months !== null
      ? 'Projeção, mantida a média recente'
      : 'Aguardando histórico suficiente'

  return (
    <Card padding="p-0" className="overflow-hidden">
      <div className="bg-[linear-gradient(135deg,var(--color-surface)_0%,var(--color-brand-primary-light)_100%)] p-4 sm:p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-brand-primary)]">
              Retorno do investimento
            </p>
            <p className="mt-2 text-sm leading-6 text-gray-600">
              Quanto do CAPEX já voltou em economia consolidada.
            </p>
          </div>
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 shadow-sm sm:min-w-40 sm:text-right">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Payback</p>
            <p className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-gray-950">
              {paybackLabel}
            </p>
            <p className="mt-1 text-xs leading-5 text-gray-500">{paybackSupportingText}</p>
          </div>
        </div>

        <div className="mt-5">
          <div className="flex items-end justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">ROI acumulado</p>
              <p className="mt-1 text-4xl font-bold tabular-nums tracking-tight text-gray-950">
                {formatNumber(roiPercent, 1)}
                <span className="ml-1 text-base font-semibold text-gray-500">%</span>
              </p>
            </div>
            <span className="rounded-full bg-[var(--color-surface)] px-3 py-1 text-xs font-semibold text-[var(--color-brand-primary)] shadow-sm">
              Progresso financeiro
            </span>
          </div>

          {/* Cor de preenchimento `brand-primary` deliberadamente: é progresso
              financeiro, não estado de saúde. `success` sugeriria "está tudo bem",
              o que este indicador não afirma (ADR-067, Decisão item 7). */}
          <div
            className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-[var(--color-chart-track)] shadow-inner"
            role="progressbar"
            aria-valuenow={barPercent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Progresso do acumulado em direção ao investimento"
          >
            <div
              className="h-full rounded-full bg-[var(--color-brand-primary)] transition-[width] duration-500 ease-out motion-reduce:transition-none"
              style={{ width: `${barPercent}%` }}
            />
          </div>
        </div>
      </div>

      <div className="p-4 sm:p-5">
        <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-3">
            <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Investido</dt>
            <dd className="mt-1 font-semibold tabular-nums text-gray-900">
              {formatCurrency(financialReturn.investment_amount_brl)}
            </dd>
          </div>
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-3">
            <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Economia acumulada</dt>
            <dd className="mt-1 font-semibold tabular-nums text-gray-900">
              {formatCurrency(financialReturn.accumulated_savings_brl)}
            </dd>
          </div>
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-3">
            <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Média mensal</dt>
            <dd className="mt-1 font-semibold tabular-nums text-gray-900">
              {formatCurrency(financialReturn.average_monthly_savings_brl)}
            </dd>
          </div>
        </dl>

        {/* Rótulo de cobertura: parte do contrato de honestidade do indicador, não
            um detalhe de UI — sem ele o ROI parece mais completo do que é (ADR-067,
            Decisão item 7). */}
        {coverage && <p className="mt-3 text-xs text-gray-500">{coverage}</p>}

        <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-4 py-3">
          {financialReturn.payback_unavailable_reason !== null ? (
            <p className="text-sm text-gray-600">
              {paybackUnavailableMessage(financialReturn.payback_unavailable_reason)}
            </p>
          ) : paybackReached ? (
            <p className="text-sm font-semibold text-[var(--color-success-text)]">
              Investimento já recuperado.
            </p>
          ) : financialReturn.payback_projection_months !== null ? (
            <>
              <p className="text-sm text-gray-900">
                <span className="font-semibold">Projeção de payback:</span>{' '}
                <span className="tabular-nums">{financialReturn.payback_projection_months}</span> ciclos.
              </p>
              {/* Sempre rotulado como PROJEÇÃO, com a premissa visível — nunca uma
                  data certa (ADR-067, Decisão item 7). */}
              <p className="mt-1 text-xs text-gray-500">
                Projeção, mantida a média de economia dos últimos ciclos.
              </p>
            </>
          ) : null}
        </div>
      </div>
    </Card>
  )
}
