import type { Diagnostic } from '../lib/dashboard/contracts'
import { SEVERITY_BG, SEVERITY_TEXT } from '../lib/dashboard/visuals'

// Resumo compacto de atenção para o `HeroCard` — sinaliza a existência de
// diagnósticos críticos sem o usuário precisar rolar até a seção de
// diagnósticos para saber que algo está errado (ver P1-06 na auditoria de
// UI/UX). Não duplica o `DiagnosticsCard` inteiro, só a contagem + uma âncora
// para lá. Zero diagnósticos CRITICAL significa nada renderizado — este chip
// existe para o caso mais urgente, não para qualquer desvio menor (esses
// continuam só na lista completa).
export function AttentionSummary({ diagnostics }: { diagnostics: Diagnostic[] }) {
  const criticalCount = diagnostics.filter((d) => d.severity === 'CRITICAL').length
  const warningCount = diagnostics.filter((d) => d.severity === 'WARNING').length

  if (criticalCount === 0) return null

  const label =
    warningCount > 0
      ? `${criticalCount} crítico${criticalCount > 1 ? 's' : ''}, ${warningCount} atenção`
      : `${criticalCount} crítico${criticalCount > 1 ? 's' : ''}`

  return (
    <a
      href="#diagnosticos"
      className={`mt-2 inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition-colors duration-150 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-danger)] ${SEVERITY_BG.danger} ${SEVERITY_TEXT.danger}`}
    >
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-danger)]" />
      {label} — ver diagnósticos
    </a>
  )
}
