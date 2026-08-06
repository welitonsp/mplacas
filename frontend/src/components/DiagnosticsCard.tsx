import type { Diagnostic } from '../lib/dashboard/contracts'
import { DIAGNOSTIC_SEVERITY_META, SEVERITY_BG, SEVERITY_BORDER_L, SEVERITY_TEXT } from '../lib/dashboard/visuals'
import { Card } from './Card'

// Cada item mostra problema → severidade → ação recomendada, nessa ordem: o usuário
// precisa entender POR QUE uma ação é recomendada antes de ver a ação em si. A lista
// já vem ordenada por gravidade (mais crítico primeiro, ver contracts.combineDiagnostics),
// e substitui o antigo PriorityActionsCard — a `recommended_action` de cada diagnóstico
// é exatamente o que compunha `priority_actions` no backend (ver
// intelligence/executive_service.py::_priority_actions), então listar o diagnóstico
// completo não perde informação, só adiciona contexto.
export function DiagnosticsCard({ diagnostics }: { diagnostics: Diagnostic[] }) {
  if (diagnostics.length === 0) {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Diagnósticos</p>
        <p className="mt-3 text-sm text-gray-500">Nenhum diagnóstico neste ciclo.</p>
      </Card>
    )
  }

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Diagnósticos</p>
      <ul className="mt-3 space-y-3">
        {diagnostics.map((diagnostic) => {
          const meta = DIAGNOSTIC_SEVERITY_META[diagnostic.severity]
          return (
            <li
              key={diagnostic.code}
              className={`rounded-lg border border-gray-200 border-l-4 ${SEVERITY_BORDER_L[meta.severity]} p-3`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold ${SEVERITY_BG[meta.severity]} ${SEVERITY_TEXT[meta.severity]}`}
                >
                  {meta.label}
                </span>
                <span className="text-sm text-gray-800">{diagnostic.message}</span>
              </div>
              <p className="mt-2 text-sm text-gray-600">
                <span className="font-medium text-gray-500">Ação recomendada: </span>
                {diagnostic.recommended_action}
              </p>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
