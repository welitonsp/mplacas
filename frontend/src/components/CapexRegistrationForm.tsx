import { FormEvent, useState } from 'react'
import { updateFinancialConfiguration } from '../lib/api'

// Diálogo inline de cadastro do CAPEX, acionado a partir do próprio estado
// `INVESTMENT_NOT_REGISTERED` da seção de ROI (ADR-067, Decisão item 7). Não é um
// modal nem uma área de configurações nova — o usuário encontra o campo exatamente
// onde sente a falta dele.
//
// Gate de perfil ADMIN: o frontend hoje não tem NENHUM mecanismo de distinção de
// papel (ver `AuthContext`/`lib/auth.ts` — o token de acesso é armazenado apenas
// como string opaca, nunca decodificado). Introduzir um mecanismo novo só para este
// formulário contrariaria a instrução de não inventar um mecanismo — então este
// formulário fica visível para qualquer usuário autenticado, e a fronteira de
// autorização real permanece no backend: `PATCH .../financial-configuration` usa
// `AdminPlantPath`, que devolve 403 para credencial READ (ver `plants/router.py`).
// Uma credencial READ vê o formulário e recebe a mensagem de erro abaixo ao
// submeter — não é o ideal de UX descrito no ADR, e fica documentado como limitação
// conhecida a resolver quando o frontend ganhar um mecanismo de papel.
export function CapexRegistrationForm({
  plantId,
  onSuccess,
}: {
  plantId: string
  onSuccess: () => void
}) {
  const [amount, setAmount] = useState('')
  const [recordedOn, setRecordedOn] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    const normalizedAmount = amount.replace(',', '.').trim()
    const numericAmount = Number(normalizedAmount)
    if (!normalizedAmount || !Number.isFinite(numericAmount) || numericAmount <= 0) {
      setError('Informe um valor investido maior que zero.')
      return
    }

    setSubmitting(true)
    try {
      const response = await updateFinancialConfiguration(plantId, {
        investment_amount_brl: normalizedAmount,
        ...(recordedOn ? { investment_recorded_on: recordedOn } : {}),
      })
      if (!response.ok) {
        if (response.status === 403) {
          setError('Seu perfil não tem permissão para cadastrar o valor investido.')
        } else if (response.status === 404) {
          setError('Usina não encontrada.')
        } else {
          setError('Não foi possível salvar o valor investido. Tente novamente.')
        }
        return
      }
      setAmount('')
      setRecordedOn('')
      onSuccess()
    } catch {
      setError('Não foi possível salvar o valor investido. Tente novamente.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="mt-4 space-y-3" aria-label="Cadastrar investimento">
      <div>
        <label htmlFor="capex-amount" className="block text-xs font-medium text-gray-700 mb-1">
          Valor investido (R$)
        </label>
        <input
          id="capex-amount"
          type="text"
          inputMode="decimal"
          required
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          disabled={submitting}
          placeholder="48000.00"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-500 transition-colors duration-150 focus:border-[var(--color-brand-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-primary)] focus-visible:ring-2 disabled:opacity-50"
        />
      </div>

      <div>
        <label htmlFor="capex-recorded-on" className="block text-xs font-medium text-gray-700 mb-1">
          Data do investimento (opcional)
        </label>
        <input
          id="capex-recorded-on"
          type="date"
          value={recordedOn}
          onChange={(e) => setRecordedOn(e.target.value)}
          disabled={submitting}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 transition-colors duration-150 focus:border-[var(--color-brand-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-primary)] focus-visible:ring-2 disabled:opacity-50"
        />
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg bg-[var(--color-danger-light)] border border-[var(--color-danger)]/30 px-3 py-2 text-sm text-[var(--color-danger-text)]"
        >
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="inline-flex min-h-[40px] items-center justify-center gap-2 rounded-lg bg-[var(--color-brand-primary)] px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-[var(--color-brand-primary-dark)] hover:shadow-md active:translate-y-0 focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-primary)] focus:ring-offset-2 focus:ring-offset-[var(--color-surface)] focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-sm motion-reduce:transition-none"
      >
        {submitting && (
          <span
            aria-hidden="true"
            className="h-3.5 w-3.5 rounded-full border-2 border-white/45 border-t-white animate-spin"
          />
        )}
        {submitting ? 'Salvando...' : 'Cadastrar investimento'}
      </button>
    </form>
  )
}
