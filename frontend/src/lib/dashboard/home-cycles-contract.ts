// Leitura mínima de `GET /reports/monthly/history` para o Início: só mês de
// referência, fim do ciclo e três campos da conferência da distribuidora.
// Parser próprio e minúsculo de propósito: importar `monthly-history-contracts`
// colocaria o parser inteiro num chunk compartilhado e estouraria o orçamento
// de "demais chunks". Qualquer forma inesperada lança — e o Início, sem
// histórico, simplesmente não mostra as tarefas novas (nunca adivinha).

import type { UtilityCheckVerdict } from './monthly-history-contracts'
import type { HomeCycleSummary } from './home'

const VERDICTS: readonly string[] = ['OK', 'SUSPECT', 'LOSS', 'IMPOSSIBLE', 'UNVERIFIABLE']

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function fail(key: string): never {
  throw new Error(`Resposta inválida da API: ${key}`)
}

// Decimal serializado como string; ausente ou ilegível vira `null`, nunca 0.
function decimalOrNull(value: unknown): number | null {
  if (typeof value !== 'string' || value.trim() === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function parseCycle(value: unknown): HomeCycleSummary {
  if (!isRecord(value)) fail('cycles[]')
  const month = value.reference_month
  if (typeof month !== 'string' || !/^\d{4}-\d{2}$/.test(month)) fail('reference_month')
  const end = value.cycle_end
  const cycleEnd = typeof end === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(end) ? end : null

  const raw = value.utility_check
  let check: HomeCycleSummary['check'] = null
  if (isRecord(raw)) {
    // Veredito novo no servidor vira "sem conferência", como no parser completo.
    const verdict = (VERDICTS.includes(raw.verdict as string) ? raw.verdict : 'UNVERIFIABLE') as UtilityCheckVerdict
    check = {
      verdict,
      missingCreditsKwh: decimalOrNull(raw.missing_credits_kwh),
      lossConfirmed: raw.loss_confirmed === true,
    }
  }
  return { referenceMonth: month, cycleEnd, check }
}

export function parseHomeCycles(payload: unknown): HomeCycleSummary[] {
  if (!isRecord(payload) || !Array.isArray(payload.cycles)) fail('cycles')
  return payload.cycles.map(parseCycle)
}
