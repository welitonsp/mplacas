import { useState } from 'react'
import { fetchLatestExplanation } from '../lib/api'
import {
  classifyExplanationErrorStatus,
  explanationSourceLabel,
  parseLatestExplanation,
  type ExplanationFetchError,
  type LatestExplanation,
} from '../lib/dashboard/explanation-contracts'
import { LoadingAnnouncement } from './LoadingAnnouncement'

type PanelStatus = 'idle' | 'loading' | 'success' | 'error'

// Painel de explicação por IA, sob demanda (T4, plano de auditoria
// 2026-08-12) — `GET /energy/explanations/latest`. Só busca ao clique
// explícito do usuário: diferente dos demais recursos da página (que
// carregam ao montar via `usePlantResource`), este NUNCA dispara sozinho —
// guarda inegociável da tarefa. Vive dentro de `DiagnosticsCard` porque o
// backend monta a explicação a partir do mesmo `build_executive_dashboard`
// que alimenta os diagnósticos já listados ali (mesma evidência, duas
// apresentações — igual à relação entre `AttentionSummary` e
// `DiagnosticsCard`).
//
// A IA aqui só INTERPRETA em texto os diagnósticos que `DiagnosticsCard` já
// mostra — nunca produz um número novo (guarda inegociável: se a explicação
// algum dia divergisse do determinístico exibido acima, o determinístico
// prevaleceria; como este painel não calcula nada, não há divergência
// possível a evitar em código, só o cuidado de nunca desenhar o texto como
// se fosse a fonte do dado). `explanationSourceLabel` + a caixa tracejada
// abaixo deixam sempre visível que é camada interpretativa, não dado
// auditável (mesmo vocabulário visual de "estimativa" já usado no projeto —
// ver `Card dashed`/`EnergyFlowDiagram`).
export function AiExplanationPanel({ plantId }: { plantId: string }) {
  const [status, setStatus] = useState<PanelStatus>('idle')
  const [explanation, setExplanation] = useState<LatestExplanation | null>(null)
  const [error, setError] = useState<ExplanationFetchError | 'UNKNOWN' | null>(null)

  const loading = status === 'loading'

  async function handleRequest() {
    setStatus('loading')
    setError(null)
    try {
      const response = await fetchLatestExplanation(plantId)
      if (!response.ok) {
        const classified = classifyExplanationErrorStatus(response.status)
        if (classified === null) {
          // 401 — `apiFetch` já tentou refresh; se ainda assim falhou, o
          // usuário está sendo deslogado. Nada específico deste painel a
          // comunicar, volta a ficar em repouso.
          setStatus('idle')
          return
        }
        setError(classified)
        setStatus('error')
        return
      }
      const parsed = parseLatestExplanation(await response.json())
      setExplanation(parsed)
      setStatus('success')
    } catch {
      // Falha de rede ou payload malformado (`parseLatestExplanation`
      // lançou) — mesma categoria "algo quebrou" que um 5xx.
      setError('UNKNOWN')
      setStatus('error')
    }
  }

  return (
    <div className="mt-4 border-t border-[var(--color-border)] pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Explicação por IA</p>
          <p className="mt-1 text-xs text-gray-500">
            Interpretação opcional, gerada sob demanda, dos diagnósticos acima — nunca é o dado oficial.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRequest}
          disabled={loading}
          aria-busy={loading}
          className="inline-flex min-h-[44px] shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--color-brand-primary)]/25 bg-[var(--color-brand-primary-light)] px-4 text-sm font-semibold text-[var(--color-brand-primary)] shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 motion-reduce:transition-none"
        >
          {loading && (
            <span
              aria-hidden="true"
              className="h-3.5 w-3.5 rounded-full border-2 border-[var(--color-brand-primary)]/40 border-t-[var(--color-brand-primary)] animate-spin"
            />
          )}
          {loading ? 'Gerando explicação...' : explanation ? 'Pedir nova explicação' : 'Pedir explicação por IA'}
        </button>
      </div>

      <LoadingAnnouncement active={loading} message="Gerando explicação por IA, aguarde." />

      {status === 'error' && error && (
        <p role="alert" className="mt-3 text-xs text-[var(--color-danger-text)]">
          {error === 'NOT_FOUND'
            ? 'Ainda não há ciclo de faturamento confirmado para explicar — assim que a primeira fatura for consolidada, a explicação fica disponível aqui.'
            : 'Não foi possível gerar a explicação agora. Tente novamente.'}
        </p>
      )}

      {status === 'success' && explanation && (
        <div
          role="region"
          aria-label="Explicação interpretativa por IA"
          className="mt-3 rounded-2xl border border-dashed border-[var(--color-chart-reference)] bg-[var(--color-surface-subtle)] p-4"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-[var(--color-chart-reference)]/40 bg-[var(--color-surface)] px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
              {explanationSourceLabel(explanation.source)}
            </span>
            <span className="text-xs text-gray-500">Camada interpretativa — não é dado auditável</span>
          </div>

          <p className="mt-3 text-sm font-semibold text-gray-800">{explanation.summary}</p>
          <p className="mt-2 text-sm leading-6 text-gray-600">{explanation.what_it_means}</p>

          {explanation.next_steps.length > 0 && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-gray-600">
              {explanation.next_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          )}

          <p className="mt-3 text-xs italic text-gray-500">{explanation.disclaimer}</p>
        </div>
      )}
    </div>
  )
}
