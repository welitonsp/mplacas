import type { AnomalyLevel, DiagnosticSeverity, Severity, TrendDirection } from './contracts'
import type { EvidenceLevel, LossCategory } from './photovoltaic-contracts'

// Status é calculado no backend (ver intelligence/executive_service.py) — o front
// apenas mapeia o mesmo vocabulário para rótulo pt-BR e cor de severidade, sem
// reimplementar os limiares de health_score.
const STATUS_META: Record<string, { label: string; severity: Severity }> = {
  HEALTHY: { label: 'Saudável', severity: 'success' },
  ATTENTION: { label: 'Atenção', severity: 'warning' },
  CRITICAL: { label: 'Crítico', severity: 'danger' },
}

export function statusMeta(status: string): { label: string; severity: Severity } {
  return STATUS_META[status] ?? { label: status, severity: 'neutral' }
}

// Tokens de TEXTO (`-text`), não os de preenchimento — `--color-success`/
// `--color-warning`/`--color-danger` continuam usados em `SEVERITY_BG`/
// `SEVERITY_BAR`/`SEVERITY_DOT`/`SEVERITY_BORDER_L` abaixo, sem alteração.
// Ver `--color-*-text` em `index.css` para a medição de contraste (P1-03).
export const SEVERITY_TEXT: Record<Severity, string> = {
  success: 'text-[var(--color-success-text)]',
  warning: 'text-[var(--color-warning-text)]',
  danger: 'text-[var(--color-danger-text)]',
  neutral: 'text-gray-600',
}

export const SEVERITY_BG: Record<Severity, string> = {
  success: 'bg-[var(--color-success-light)]',
  warning: 'bg-[var(--color-warning-light)]',
  danger: 'bg-[var(--color-danger-light)]',
  neutral: 'bg-gray-100',
}

export const SEVERITY_BORDER_L: Record<Severity, string> = {
  success: 'border-l-[var(--color-success)]',
  warning: 'border-l-[var(--color-warning)]',
  danger: 'border-l-[var(--color-danger)]',
  neutral: 'border-l-gray-300',
}

export const SEVERITY_BAR: Record<Severity, string> = {
  success: 'bg-[var(--color-success)]',
  warning: 'bg-[var(--color-warning)]',
  danger: 'bg-[var(--color-danger)]',
  neutral: 'bg-gray-400',
}

export const SEVERITY_DOT: Record<Severity, string> = {
  success: 'bg-[var(--color-success)]',
  warning: 'bg-[var(--color-warning)]',
  danger: 'bg-[var(--color-danger)]',
  neutral: 'bg-gray-400',
}

// Rótulo textual da severidade do diagnóstico — sempre exibido junto da cor (ver
// skill frontend-design, regra de acessibilidade: cor sozinha não basta).
export const DIAGNOSTIC_SEVERITY_META: Record<DiagnosticSeverity, { label: string; severity: Severity }> = {
  CRITICAL: { label: 'Crítico', severity: 'danger' },
  WARNING: { label: 'Atenção', severity: 'warning' },
  INFO: { label: 'Informativo', severity: 'neutral' },
}

export const LEVEL_LABEL: Record<AnomalyLevel, string> = {
  NORMAL: 'Normal',
  ATTENTION: 'Atenção',
  ANOMALY: 'Anomalia',
  CRITICAL: 'Crítico',
}

// Rótulo textual pareado com `levelSeverity`: `null` vira uma frase explícita
// ("Sem expectativa"), nunca `undefined`/uma chave ausente no objeto acima —
// evitar isso é o que faz `LEVEL_LABEL[activeDay.level]` quebrar quando o dia
// não tem severidade calculável (ver `AnomalyDailyPoint.level`).
export function levelLabel(level: AnomalyLevel | null): string {
  return level === null ? 'Sem expectativa' : LEVEL_LABEL[level]
}

// Mesmos limiares usados em intelligence/energy_engine.py para o desvio do ciclo
// vs. produção esperada: < 70% = PRODUCTION_WELL_BELOW_EXPECTED (CRITICAL/danger),
// < 85% = PRODUCTION_BELOW_EXPECTED (WARNING), >= 85% = dentro do esperado (success).
// Não inventar um limiar novo aqui — reaproveita o mesmo vocabulário do backend.
export function performanceSeverity(percent: number): Severity {
  if (percent < 70) return 'danger'
  if (percent < 85) return 'warning'
  return 'success'
}

// NORMAL = produção dentro do esperado (bom). ATTENTION = desvio leve.
// ANOMALY/CRITICAL = desvio relevante — mesma cor de alerta para os dois,
// diferenciados pelo rótulo textual (ver LEVEL_LABEL), sem inventar um quinto tom.
// `null` = sem expectativa disponível pra calcular severidade nesse dia (ex.:
// usina sem baseline sazonal ainda, mas com produção real coletada) — tom
// neutro, nunca um "bom"/"ruim" fabricado a partir de um dado ausente.
export function levelSeverity(level: AnomalyLevel | null): Severity {
  if (level === null) return 'neutral'
  if (level === 'NORMAL') return 'success'
  if (level === 'ATTENTION') return 'warning'
  return 'danger'
}

export type TrendMetricKey = 'production' | 'total_consumption' | 'imported_energy'

// O sentido de "bom"/"ruim" depende da métrica: produção subir é bom, energia
// importada subir é ruim, e consumo total não tem um sentido óbvio de bom/ruim
// (não pintamos essa métrica). Não usar DOWN=vermelho/UP=verde de forma cega.
const GOOD_DIRECTION: Record<TrendMetricKey, TrendDirection | null> = {
  production: 'UP',
  imported_energy: 'DOWN',
  total_consumption: null,
}

export function trendSeverity(metricKey: TrendMetricKey, direction: TrendDirection): Severity {
  const good = GOOD_DIRECTION[metricKey]
  if (good === null || direction === 'STABLE') return 'neutral'
  return direction === good ? 'success' : 'danger'
}

export const DIRECTION_SYMBOL: Record<TrendDirection, string> = { UP: '▲', DOWN: '▼', STABLE: '▬' }
export const DIRECTION_TEXT: Record<TrendDirection, string> = {
  UP: 'aumentou',
  DOWN: 'diminuiu',
  STABLE: 'estável',
}

export const ANOMALY_LEGEND: { level: AnomalyLevel; label: string }[] = [
  { level: 'NORMAL', label: 'Normal' },
  { level: 'ATTENTION', label: 'Atenção' },
  { level: 'ANOMALY', label: 'Anomalia/crítico' },
]

// Nomes em pt-BR para as oito categorias da taxonomia de perdas fotovoltaicas
// (`photovoltaic/loss_taxonomy.py::LossCategory`, ver ADR-065 seção 4).
export const LOSS_CATEGORY_LABEL: Record<LossCategory, string> = {
  COMMUNICATION: 'Comunicação (dados ausentes)',
  UNAVAILABILITY: 'Indisponibilidade',
  CLIPPING: 'Clipping (limite do inversor)',
  SOILING: 'Sujeira (soiling)',
  SHADING: 'Sombreamento',
  TEMPERATURE: 'Temperatura',
  DEGRADATION: 'Degradação',
  UNEXPLAINED: 'Não explicada',
}

// `evidence_level` é a ressalva epistêmica de cada categoria (ADR-065 seção 3):
// LIKELY = evidência de que a causa está presente (mais preocupante), POSSIBLE
// = evidência parcial, NOT_DETECTED = evidência de que a causa NÃO está
// presente (bom sinal), NOT_ASSESSABLE = não foi possível avaliar (neutro, não
// é nem bom nem ruim). Cor sempre acompanhada do rótulo textual.
export const EVIDENCE_LEVEL_META: Record<EvidenceLevel, { label: string; severity: Severity }> = {
  LIKELY: { label: 'Evidência de causa', severity: 'danger' },
  POSSIBLE: { label: 'Possível causa', severity: 'warning' },
  NOT_DETECTED: { label: 'Não detectada', severity: 'success' },
  NOT_ASSESSABLE: { label: 'Não avaliável', severity: 'neutral' },
}
