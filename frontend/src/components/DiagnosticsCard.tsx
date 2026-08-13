import type { Diagnostic } from '../lib/dashboard/contracts'
import { DIAGNOSTIC_SEVERITY_META, SEVERITY_BG, SEVERITY_BORDER_L, SEVERITY_TEXT } from '../lib/dashboard/visuals'
import { AiExplanationPanel } from './AiExplanationPanel'
import { Card } from './Card'

// Cada item mostra problema → severidade → ação recomendada. Essa ordem ajuda
// a interface funcionar como diagnóstico de causa: primeiro o usuário entende
// o motivo, depois decide o próximo passo.
//
// `plantId` alimenta `AiExplanationPanel` (T4, plano de auditoria
// 2026-08-12): a explicação por IA interpreta exatamente os diagnósticos
// mostrados aqui (mesma fonte no backend, `build_executive_dashboard`),
// por isso vive dentro deste card em vez de uma seção separada da página.
export function DiagnosticsCard({ diagnostics, plantId }: { diagnostics: Diagnostic[]; plantId: string }) {
  if (diagnostics.length === 0) {
    return (
      <Card>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Diagnósticos</p>
          <span className="rounded-full bg-[var(--color-success-light)] px-2.5 py-1 text-xs font-semibold text-[var(--color-success-text)]">
            Sem alertas
          </span>
        </div>
        <p className="mt-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-3 py-2 text-sm text-gray-500">
          Nenhum diagnóstico neste ciclo.
        </p>
        <AiExplanationPanel plantId={plantId} />
      </Card>
    )
  }

  return (
    <Card>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Diagnósticos</p>
        <span className="rounded-full bg-[var(--color-surface-subtle)] px-2.5 py-1 text-xs font-semibold text-gray-600">
          {diagnostics.length} {diagnostics.length === 1 ? 'item' : 'itens'}
        </span>
      </div>

      <ul className="mt-3 space-y-3">
        {diagnostics.map((diagnostic) => {
          const meta = DIAGNOSTIC_SEVERITY_META[diagnostic.severity]
          return (
            <li
              key={diagnostic.code}
              className={`rounded-2xl border border-gray-200 border-l-4 bg-[var(--color-surface)] ${SEVERITY_BORDER_L[meta.severity]} p-3 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md motion-reduce:transition-none`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold ${SEVERITY_BG[meta.severity]} ${SEVERITY_TEXT[meta.severity]}`}
                >
                  {meta.label}
                </span>
                <span className="text-sm font-medium text-gray-800">{diagnostic.message}</span>
              </div>
              <p className="mt-2 rounded-xl bg-[var(--color-surface-subtle)] px-3 py-2 text-sm text-gray-600">
                <span className="font-semibold text-gray-700">Ação recomendada: </span>
                {diagnostic.recommended_action}
              </p>
            </li>
          )
        })}
      </ul>

      <AiExplanationPanel plantId={plantId} />
    </Card>
  )
}
