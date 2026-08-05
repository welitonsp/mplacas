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

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Retorno do investimento</p>

      <div className="mt-2 flex items-baseline justify-between gap-3">
        <p className="text-2xl font-semibold text-gray-900 tabular-nums">
          {formatNumber(roiPercent, 1)}
          <span className="ml-1 text-sm font-normal text-gray-500">%</span>
        </p>
        <span className="shrink-0 text-xs text-gray-500">acumulado sobre o investimento</span>
      </div>

      {/* Cor de preenchimento `brand-primary` deliberadamente: é progresso
          financeiro, não estado de saúde. `success` sugeriria "está tudo bem",
          o que este indicador não afirma (ADR-067, Decisão item 7). */}
      <div
        className="mt-2 h-2 w-full overflow-hidden rounded-full bg-[var(--color-chart-track)]"
        role="progressbar"
        aria-valuenow={barPercent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Progresso do acumulado em direção ao investimento"
      >
        <div
          className="h-full rounded-full bg-[var(--color-brand-primary)]"
          style={{ width: `${barPercent}%` }}
        />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-xs text-gray-500">Investido</dt>
          <dd className="tabular-nums text-gray-900">
            {formatCurrency(financialReturn.investment_amount_brl)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500">Economia acumulada</dt>
          <dd className="tabular-nums text-gray-900">
            {formatCurrency(financialReturn.accumulated_savings_brl)}
          </dd>
        </div>
      </dl>

      {/* Rótulo de cobertura: parte do contrato de honestidade do indicador, não
          um detalhe de UI — sem ele o ROI parece mais completo do que é (ADR-067,
          Decisão item 7). */}
      {coverage && <p className="mt-3 text-xs text-gray-500">{coverage}</p>}

      <div className="mt-4 border-t border-gray-100 pt-3">
        {financialReturn.payback_unavailable_reason !== null ? (
          <p className="text-sm text-gray-500">
            {paybackUnavailableMessage(financialReturn.payback_unavailable_reason)}
          </p>
        ) : paybackReached ? (
          <p className="text-sm font-medium text-[var(--color-success-text)]">
            Investimento já recuperado.
          </p>
        ) : financialReturn.payback_projection_months !== null ? (
          <>
            <p className="text-sm text-gray-900">
              <span className="font-medium">Projeção de payback:</span>{' '}
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
    </Card>
  )
}
