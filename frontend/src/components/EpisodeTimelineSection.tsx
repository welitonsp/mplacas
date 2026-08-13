import { useState } from 'react'
import type { AnomalyFetchState, Severity } from '../lib/dashboard/contracts'
import type { ExpectedDailyProduction } from '../lib/dashboard/photovoltaic-contracts'
import { baselineUnavailableMessage } from '../lib/dashboard/photovoltaic-contracts'
import { buildAnomalyEpisodes, type AnomalyEpisode } from '../lib/dashboard/episodes'
import { LEVEL_LABEL, levelSeverity, SEVERITY_BG, SEVERITY_TEXT } from '../lib/dashboard/visuals'
import { formatFullDate } from '../lib/format'
import { Card } from './Card'
import { OperationalState } from './OperationalState'
import { RetryableError } from './RetryableError'

// Teto de itens visíveis sem expansão explícita (ADR-075, Decisão 5.5): se
// uma usina tiver mais de 10 episódios em 90 dias, o problema não é a lista.
const MAX_VISIBLE_EPISODES = 10

// Linha do tempo de episódios do módulo Produção (ADR-075, Decisão 4) —
// responde "aconteceu alguma coisa enquanto eu não olhava?", pergunta que
// nenhuma outra superfície do produto responde. Vocabulário travado:
// "Episódios"/"ocorrências", nunca "Alertas"/"Notificações"/"Central"
// (Decisão 3) — não há central de alertas, e esta seção não pode sugerir
// que há.
//
// Zero requisição nova: reusa `anomalyState`, o mesmo recurso que
// `ProductionDiagnosticPanel`/`ProductionHistorySection` já carregam
// (`GET /energy/anomalies/latest`, até 90 dias). `expectedProduction` só
// alimenta o texto do motivo quando não há baseline (mesmo padrão de
// `ProductionDiagnosticPanel`).
export function EpisodeTimelineSection({
  anomalyState,
  expectedProduction,
  onRetry,
}: {
  anomalyState: AnomalyFetchState
  // `null` = baseline sazonal ainda carregando (`/photovoltaic/summary`).
  expectedProduction: ExpectedDailyProduction | null
  // Só relevante para o estado `SERVER_ERROR` — reexecuta a busca do histórico.
  onRetry?: () => void
}) {
  const [expanded, setExpanded] = useState(false)

  if (anomalyState.loading && !anomalyState.data) {
    return (
      <Card className="animate-pulse">
        <div className="mb-3 h-3 w-1/3 rounded bg-gray-200" />
        <div className="h-16 w-full rounded bg-gray-100" />
      </Card>
    )
  }

  // 404: ainda não há dado diário coletado para o período — estado esperado
  // (usina nova, backfill pendente), mesmo tratamento de
  // `ProductionDiagnosticPanel` para o caso equivalente (nunca uma lista
  // vazia silenciosa, e nunca a afirmação positiva de "nenhuma ocorrência",
  // que exigiria dado que ainda não existe).
  if (anomalyState.error === 'NOT_FOUND') {
    return (
      <OperationalState
        role="status"
        tone="neutral"
        icon="sync"
        align="start"
        title="Sem produção diária coletada"
        description="Ainda não há dados diários suficientes para montar a linha do tempo de episódios."
      />
    )
  }

  // 5xx ou falha de rede: algo quebrou de fato — nunca confundir com "sem
  // ocorrência" (a pior saída possível desta tela: afirmar normalidade sem
  // evidência).
  if (anomalyState.error === 'SERVER_ERROR') {
    return (
      <RetryableError
        message="Não foi possível carregar os episódios de produção. Tente novamente."
        onRetry={onRetry ?? (() => {})}
      />
    )
  }

  if (!anomalyState.data) {
    return (
      <OperationalState
        role="status"
        tone="neutral"
        icon="sync"
        align="start"
        title="Episódios indisponíveis"
        description="Não foi possível carregar a linha do tempo de episódios no momento."
      />
    )
  }

  const data = anomalyState.data

  // Sem expectativa disponível para o período: o motor não classificou
  // nenhum dia, então não há como saber se houve ocorrência ou não. "Não
  // sei" é diferente de "está tudo bem" — nunca renderizar "nenhuma
  // ocorrência" aqui (ADR-075, Decisão 4.5, mesma armadilha da ADR-074,
  // Decisão 3).
  if (data.expected_unavailable_reason !== null) {
    const description = expectedProduction
      ? expectedProduction.available
        ? 'O histórico de anomalias não trouxe expectativa para o período analisado.'
        : baselineUnavailableMessage(expectedProduction.reason, expectedProduction.referenceCompleteOn)
      : 'A referência esperada ainda está carregando.'

    return (
      <OperationalState
        role="status"
        tone="neutral"
        icon="sync"
        align="start"
        title="Sem referência esperada para avaliar o período"
        description={description}
      />
    )
  }

  const episodes = buildAnomalyEpisodes(data.daily)

  if (episodes.length === 0) {
    return (
      <OperationalState
        role="status"
        tone="success"
        icon="check"
        align="start"
        title="Nenhuma ocorrência"
        description={`Nenhuma ocorrência nos últimos ${data.days_analyzed} ${
          data.days_analyzed === 1 ? 'dia analisado' : 'dias analisados'
        }.`}
      />
    )
  }

  // Mais recente primeiro (Decisão 5.5) — `buildAnomalyEpisodes` devolve em
  // ordem cronológica ascendente (mesma ordem de `daily`).
  const mostRecentFirst = [...episodes].reverse()
  const visibleEpisodes = expanded ? mostRecentFirst : mostRecentFirst.slice(0, MAX_VISIBLE_EPISODES)
  const hiddenCount = mostRecentFirst.length - visibleEpisodes.length

  return (
    <div className="space-y-3">
      <ol className="space-y-3">
        {visibleEpisodes.map((episode) => (
          <li key={`${episode.code}-${episode.startDate}`}>
            <EpisodeCard episode={episode} />
          </li>
        ))}
      </ol>
      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="min-h-[44px] rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-4 text-sm font-semibold text-[var(--color-text-secondary)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] motion-reduce:transition-none"
        >
          Mostrar mais {hiddenCount} {hiddenCount === 1 ? 'episódio' : 'episódios'}
        </button>
      )}
    </div>
  )
}

function episodeDateRangeLabel(episode: AnomalyEpisode): string {
  if (episode.startDate === episode.endDate) return formatFullDate(episode.startDate)
  return `${formatFullDate(episode.startDate)} – ${formatFullDate(episode.endDate)}`
}

function EpisodeCard({ episode }: { episode: AnomalyEpisode }) {
  const tone = levelSeverity(episode.level)

  return (
    <Card accent={tone} className={SEVERITY_BG[tone]}>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityIcon tone={tone} />
        <span className={`text-sm font-semibold ${SEVERITY_TEXT[tone]}`}>{LEVEL_LABEL[episode.level]}</span>
        <span className="text-xs font-medium text-gray-500">
          {episodeDateRangeLabel(episode)} · {episode.durationDays} {episode.durationDays === 1 ? 'dia' : 'dias'}
          {episode.ongoing ? ' · em curso' : ''}
        </span>
      </div>
      <p className="mt-2 text-sm leading-6 text-gray-700">{episode.message}</p>
      <p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{episode.recommendedAction}</p>
    </Card>
  )
}

// Ícone próprio por severidade (forma, não só cor), decorativo — o texto ao
// lado já carrega o significado pra leitor de tela. Mesmas silhuetas de
// `DeviceStatusSection.tsx::StatusIcon` (cópia local — cada componente já
// tem a sua, mesmo padrão do projeto: ver comentário de `fallbackPvSummary`
// em `ProductionPage.tsx`).
function SeverityIcon({ tone }: { tone: Severity }) {
  return (
    <span aria-hidden="true" className={`inline-flex h-4 w-4 shrink-0 ${SEVERITY_TEXT[tone]}`}>
      <svg
        viewBox="0 0 24 24"
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {tone === 'success' ? (
          <path d="m5 12 4 4L19 6" />
        ) : tone === 'warning' ? (
          <>
            <path d="M12 8v4" />
            <path d="M12 16h.01" />
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
          </>
        ) : tone === 'danger' ? (
          <>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8v5" />
            <path d="M12 16h.01" />
          </>
        ) : (
          <>
            <circle cx="12" cy="12" r="9" />
            <path d="M9.5 9a2.5 2.5 0 1 1 3.4 2.3c-.8.35-1.4.9-1.4 1.9v.3" />
            <path d="M12 17h.01" />
          </>
        )}
      </svg>
    </span>
  )
}
