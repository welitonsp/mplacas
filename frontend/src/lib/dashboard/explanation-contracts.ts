// Parser do contrato de `GET /energy/explanations/latest`
// (`explanations/router.py:27`, T4 do plano de auditoria 2026-08-12) —
// explicação em linguagem natural do estado executivo do ciclo atual
// (mesma fonte de dado de `DiagnosticsCard`: `build_executive_dashboard`).
//
// Camada interpretativa, nunca fonte de número novo (guarda inegociável da
// tarefa): o endpoint só reformula em texto os diagnósticos já calculados
// deterministicamente (`explanations/executive.py::executive_explanation_request`).
// `source` distingue as duas origens possíveis do TEXTO (nunca do número):
// - `DETERMINISTIC` — resposta fixa montada em
//   `explanations/service.py::build_deterministic_explanation`, sem nenhuma
//   chamada de rede. É o caminho usado tanto quando `explanation_api_url`
//   não está configurado (`explanations/router.py:36`, provider == None)
//   quanto quando o provedor externo está configurado mas falha
//   (`explain_with_fallback` engole a exceção e cai no mesmo determinístico,
//   `service.py:57-61`). O frontend não distingue esses dois casos — os
//   dois são "provedor de IA não disponível agora", estado normal, nunca erro.
// - `AI_ASSISTED` — o provedor externo respondeu com sucesso.
//
// Todos os campos de texto são garantidos não-vazios pelo backend
// (`GroundedExplanation.validate()`, `explanations/models.py:53-61`) — por
// isso o segundo teste obrigatório do §2.2 (campo nulo/indisponível) não tem
// um campo nulo real dentro de um payload 200 para exercitar aqui. A forma
// real de indisponibilidade deste endpoint específico é HTTP 404
// (`EnergyCycleNotFoundError`, nenhuma fatura confirmada ainda para o ciclo
// atual) — `classifyExplanationErrorStatus` abaixo cobre esse caso, mesmo
// padrão de `contracts.ts::classifyAnomalyErrorStatus`.

export type ExplanationSource = 'DETERMINISTIC' | 'AI_ASSISTED'

const EXPLANATION_SOURCES: ReadonlySet<string> = new Set(['DETERMINISTIC', 'AI_ASSISTED'])

export interface LatestExplanation {
  plant_id: string
  // Vocabulário de `ExecutiveStatus` (`intelligence/executive_service.py`) —
  // mesmo campo que `ExecutiveDashboardResponse.status` em `contracts.ts`,
  // repetido aqui porque este endpoint é buscado independentemente (sob
  // demanda), não a partir do mesmo payload.
  status: string
  source: ExplanationSource
  summary: string
  what_it_means: string
  next_steps: string[]
  disclaimer: string
  // Códigos dos diagnósticos usados como evidência (o mesmo `code` de
  // `Diagnostic` em `contracts.ts`) — nunca um código novo inventado pela
  // IA; só usado para mostrar que a explicação se apoia nos diagnósticos já
  // exibidos em `DiagnosticsCard`, não em dado extra.
  evidence_codes: string[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireString(source: Record<string, unknown>, key: string): string {
  const value = source[key]
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value
}

function requireSource(source: Record<string, unknown>, key: string): ExplanationSource {
  const value = source[key]
  if (typeof value !== 'string' || !EXPLANATION_SOURCES.has(value)) {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value as ExplanationSource
}

function requireStringArray(source: Record<string, unknown>, key: string): string[] {
  const value = source[key]
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new Error(`Resposta inválida da API: ${key}`)
  }
  return value
}

export function parseLatestExplanation(payload: unknown): LatestExplanation {
  if (!isRecord(payload)) throw new Error('Resposta inválida da API.')
  return {
    plant_id: requireString(payload, 'plant_id'),
    status: requireString(payload, 'status'),
    source: requireSource(payload, 'source'),
    summary: requireString(payload, 'summary'),
    what_it_means: requireString(payload, 'what_it_means'),
    next_steps: requireStringArray(payload, 'next_steps'),
    disclaimer: requireString(payload, 'disclaimer'),
    evidence_codes: requireStringArray(payload, 'evidence_codes'),
  }
}

// Distingue "indisponível" (nenhuma fatura confirmada ainda para o ciclo —
// `EnergyCycleNotFoundError`, HTTP 404, estado esperado para usina nova) de
// "algo quebrou" (5xx/rede — vale oferecer nova tentativa). 401 devolve
// `null`: `apiFetch` já tentou refresh; se ainda assim falhou, o usuário
// está sendo deslogado, não há nada específico deste painel a comunicar.
export type ExplanationFetchError = 'NOT_FOUND' | 'SERVER_ERROR'

export function classifyExplanationErrorStatus(status: number): ExplanationFetchError | null {
  if (status === 401) return null
  if (status === 404) return 'NOT_FOUND'
  return 'SERVER_ERROR'
}

// Rótulo visível junto do texto — nunca deixar a origem implícita (guarda
// inegociável da tarefa: a camada interpretativa precisa ficar
// visualmente/textualmente distinta do dado auditável).
export function explanationSourceLabel(source: ExplanationSource): string {
  return source === 'AI_ASSISTED' ? 'Interpretação assistida por IA' : 'Resumo determinístico do sistema'
}
