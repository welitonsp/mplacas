import type {
  EvidenceLevel,
  PhotovoltaicLossItem,
  PhotovoltaicSummaryResponse,
} from '../lib/dashboard/photovoltaic-contracts'
import { ratioToPercent } from '../lib/dashboard/photovoltaic-contracts'
import { EVIDENCE_LEVEL_META, LOSS_CATEGORY_LABEL, SEVERITY_BG, SEVERITY_TEXT } from '../lib/dashboard/visuals'
import type { Severity } from '../lib/dashboard/contracts'
import { formatNumber, toNumber } from '../lib/format'
import { Card } from './Card'
import { OperationalState } from './OperationalState'

interface TechnicalDiagnosis {
  tone: Severity
  title: string
  confidence: 'Alta' | 'Média' | 'Baixa'
  investigationWindow?: string
  owner?: string
  cause: string
  impact: string
  action: string
  evidenceSummary?: string
  playbook?: Array<{ title: string; detail: string }>
  signals: Array<{ label: string; value: string; tone: Severity }>
}

const EVIDENCE_RANK: Record<EvidenceLevel, number> = {
  LIKELY: 0,
  POSSIBLE: 1,
  NOT_DETECTED: 2,
  NOT_ASSESSABLE: 3,
}

function formatPercent(value: number | null, maximumFractionDigits = 0): string {
  return value === null ? '—' : `${formatNumber(value, maximumFractionDigits)}%`
}

function signalTone(value: number | null, warning: number, danger: number): Severity {
  if (value === null) return 'neutral'
  if (value < danger) return 'danger'
  if (value < warning) return 'warning'
  return 'success'
}

function strongestLoss(losses: PhotovoltaicLossItem[] | null): PhotovoltaicLossItem | null {
  if (losses === null) return null
  const candidates = losses
    .filter((loss) => loss.evidence_level === 'LIKELY' || loss.evidence_level === 'POSSIBLE')
    .sort((left, right) => {
      const evidenceDelta = EVIDENCE_RANK[left.evidence_level] - EVIDENCE_RANK[right.evidence_level]
      if (evidenceDelta !== 0) return evidenceDelta
      return (toNumber(right.estimated_loss_percent) ?? -1) - (toNumber(left.estimated_loss_percent) ?? -1)
    })
  return candidates[0] ?? null
}

function defaultPlaybook(tone: Severity): Array<{ title: string; detail: string }> {
  if (tone === 'danger') {
    return [
      { title: 'Confirmar telemetria', detail: 'Verificar inversor, gateway e coleta antes de concluir perda física.' },
      { title: 'Isolar causa dominante', detail: 'Cruzar PR bruto, PR corrigido, disponibilidade e perdas estimadas.' },
      { title: 'Medir pós-ação', detail: 'Registrar correção e comparar a leitura do próximo ciclo.' },
    ]
  }

  if (tone === 'warning') {
    return [
      { title: 'Validar tendência', detail: 'Comparar com dias e ciclos equivalentes antes de acionar campo.' },
      { title: 'Preparar inspeção', detail: 'Deixar causa provável, evidências e limite de decisão documentados.' },
      { title: 'Revisar próximo ciclo', detail: 'Confirmar se o sinal cresceu, estabilizou ou desapareceu.' },
    ]
  }

  if (tone === 'success') {
    return [
      { title: 'Manter baseline', detail: 'Usar este ciclo como referência saudável para desvios futuros.' },
      { title: 'Preservar rotina', detail: 'Continuar monitorando PR, disponibilidade e degradação.' },
      { title: 'Registrar aprendizado', detail: 'Guardar contexto que sustentou a boa performance.' },
    ]
  }

  return [
    { title: 'Completar dados', detail: 'Aguardar ou recuperar leituras necessárias para fechar diagnóstico.' },
    { title: 'Evitar conclusão prematura', detail: 'Não transformar ausência de dado em causa técnica.' },
    { title: 'Reavaliar depois', detail: 'Refazer a leitura quando performance, baseline e perdas estiverem disponíveis.' },
  ]
}

export function buildTechnicalDiagnosis(summary: PhotovoltaicSummaryResponse | null): TechnicalDiagnosis {
  if (summary === null) {
    return {
      tone: 'neutral',
      title: 'Montando diagnóstico',
      confidence: 'Baixa',
      cause: 'Aguardando leitura técnica da usina.',
      impact: 'Os indicadores ainda estão sendo carregados para evitar conclusão prematura.',
      action: 'Aguarde a atualização automática ou use atualizar se a coleta demorar mais que o normal.',
      signals: [
        { label: 'PR bruto', value: '—', tone: 'neutral' },
        { label: 'Disponibilidade', value: '—', tone: 'neutral' },
        { label: 'PR corrigido', value: '—', tone: 'neutral' },
      ],
    }
  }

  const pr = ratioToPercent(summary.performance?.performance_ratio ?? null)
  const correctedPr = ratioToPercent(summary.performance?.temperature_corrected_performance_ratio ?? null)
  const availability = ratioToPercent(summary.performance?.reporting_availability_ratio ?? null)
  const annualizedDegradation = toNumber(summary.baseline?.annualized_degradation_percent ?? null)
  const loss = strongestLoss(summary.losses)
  const lossValue = loss ? toNumber(loss.estimated_loss_percent) : null
  const confidence: TechnicalDiagnosis['confidence'] =
    loss?.evidence_level === 'LIKELY' ? 'Alta' : loss?.evidence_level === 'POSSIBLE' ? 'Média' : 'Baixa'

  const signals: TechnicalDiagnosis['signals'] = [
    { label: 'PR bruto', value: formatPercent(pr), tone: signalTone(pr, 85, 70) },
    { label: 'Disponibilidade', value: formatPercent(availability), tone: signalTone(availability, 95, 85) },
    { label: 'PR corrigido', value: formatPercent(correctedPr), tone: signalTone(correctedPr, 85, 70) },
  ]

  if (annualizedDegradation !== null) {
    const degradationTone: Severity =
      annualizedDegradation <= -2 ? 'danger' : annualizedDegradation <= -1 ? 'warning' : 'success'
    signals.push({
      label: 'Degradação anual',
      value: `${formatNumber(annualizedDegradation, 1)}%`,
      tone: degradationTone,
    })
  }

  if (availability !== null && availability < 85) {
    return {
      tone: 'danger',
      title: 'Diagnóstico: telemetria crítica',
      confidence: 'Alta',
      cause: 'A principal hipótese é falha de comunicação ou indisponibilidade de device.',
      impact: 'A leitura técnica fica menos confiável e pode esconder perda real de geração.',
      action: 'Priorizar checagem de inversor, gateway, conectividade e lacunas de coleta antes de avaliar sujeira ou degradação.',
      signals,
    }
  }

  if (pr !== null && pr < 70) {
    return {
      tone: 'danger',
      title: 'Diagnóstico: performance crítica',
      confidence,
      cause: loss
        ? `A causa mais forte no momento é ${LOSS_CATEGORY_LABEL[loss.category].toLowerCase()}.`
        : 'A produção está muito abaixo da referência, mas a causa ainda não foi isolada.',
      impact: `Risco alto de perda operacional no ciclo${lossValue !== null ? `; a suspeita principal explica cerca de ${formatPercent(lossValue, 1)}` : ''}.`,
      action: loss
        ? 'Abrir investigação em campo começando pela causa mais provável e validar se o PR corrigido confirma perda não climática.'
        : 'Cruzar PR, disponibilidade, histórico de produção e inspeção visual para separar clima, falha de medição e perda física.',
      signals,
    }
  }

  if (loss && loss.evidence_level === 'LIKELY') {
    const meta = EVIDENCE_LEVEL_META[loss.evidence_level]
    return {
      tone: meta.severity,
      title: 'Diagnóstico: causa provável localizada',
      confidence: 'Alta',
      cause: `${LOSS_CATEGORY_LABEL[loss.category]} é a hipótese técnica dominante.`,
      impact:
        lossValue === null
          ? 'Existe evidência de causa, mas o impacto percentual ainda não é estimável com segurança.'
          : `Impacto estimado de ${formatPercent(lossValue, 1)} sobre a performance avaliada.`,
      action: 'Transformar esta causa em ordem de verificação: validar evidência, registrar achado e comparar PR após correção.',
      signals,
    }
  }

  if (loss && loss.evidence_level === 'POSSIBLE') {
    return {
      tone: 'warning',
      title: 'Diagnóstico: suspeita em observação',
      confidence: 'Média',
      cause: `${LOSS_CATEGORY_LABEL[loss.category]} aparece como possível causa, ainda sem evidência conclusiva.`,
      impact:
        lossValue === null
          ? 'O impacto ainda é incerto; acompanhe a repetição do padrão antes de acionar campo.'
          : `Possível impacto de ${formatPercent(lossValue, 1)} se o padrão se repetir nos próximos ciclos.`,
      action: 'Monitorar tendência, comparar dias similares de irradiância e preparar inspeção se o sinal persistir.',
      signals,
    }
  }

  if (pr !== null && availability !== null && pr >= 85 && availability >= 95) {
    return {
      tone: 'success',
      title: 'Diagnóstico: operação saudável',
      confidence: 'Alta',
      cause: 'Não há causa técnica relevante detectada neste ciclo.',
      impact: 'A performance e a disponibilidade sustentam uma leitura confiável da usina.',
      action: 'Manter acompanhamento e usar este ciclo como referência para comparar desvios futuros.',
      signals,
    }
  }

  return {
    tone: 'neutral',
    title: 'Diagnóstico: leitura inconclusiva',
    confidence: 'Baixa',
    cause: 'Os dados disponíveis ainda não apontam uma causa dominante.',
    impact: 'A decisão operacional deve ser conservadora até completar performance, baseline e perdas.',
    action: 'Completar histórico técnico e revisar novamente quando houver dados suficientes de PR, disponibilidade e perdas.',
    signals,
  }
}

export function TechnicalDiagnosticPanel({ summary }: { summary: PhotovoltaicSummaryResponse | null }) {
  const diagnosis = buildTechnicalDiagnosis(summary)

  if (summary === null) {
    return (
      <OperationalState
        role="status"
        tone="neutral"
        icon="sync"
        align="start"
        eyebrow="Diagnóstico de causa"
        title="Montando diagnóstico técnico"
        description="Ainda estamos carregando PR, disponibilidade, perdas e baseline. A leitura fica em modo conservador para evitar conclusão prematura."
        actionClassName="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3"
        action={
          <>
            {diagnosis.signals.map((signal) => (
              <div
                key={signal.label}
                className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-3 py-2"
              >
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{signal.label}</p>
                <p className="mt-1 text-sm font-semibold text-[var(--color-text-secondary)]">{signal.value}</p>
              </div>
            ))}
          </>
        }
      />
    )
  }

  const investigationWindow =
    diagnosis.investigationWindow ??
    (diagnosis.tone === 'danger'
      ? 'Agir hoje'
      : diagnosis.tone === 'warning'
        ? 'Acompanhar esta semana'
        : diagnosis.tone === 'success'
          ? 'Rotina semanal'
          : 'Completar dados')
  const owner =
    diagnosis.owner ??
    (diagnosis.tone === 'danger'
      ? 'Técnico + operação'
      : diagnosis.tone === 'warning'
        ? 'Operação'
        : diagnosis.tone === 'success'
          ? 'Gestão técnica'
          : 'Operação')
  const evidenceSummary =
    diagnosis.evidenceSummary ??
    diagnosis.signals.map((signal) => `${signal.label}: ${signal.value}`).join(' · ')
  const playbook = diagnosis.playbook ?? defaultPlaybook(diagnosis.tone)

  return (
    <Card accent={diagnosis.tone} className="overflow-hidden">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Diagnóstico de causa</p>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${SEVERITY_BG[diagnosis.tone]} ${SEVERITY_TEXT[diagnosis.tone]}`}
            >
              Confiança {diagnosis.confidence.toLowerCase()}
            </span>
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
              {investigationWindow}
            </span>
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
              {owner}
            </span>
          </div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight text-gray-950">{diagnosis.title}</h2>
          <p className="mt-2 text-sm leading-6 text-gray-600">{diagnosis.cause}</p>
        </div>

        <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-4 lg:min-w-[360px]">
          {diagnosis.signals.map((signal) => (
            <div
              key={signal.label}
              className={`rounded-2xl border border-[var(--color-border)] ${SEVERITY_BG[signal.tone]} px-3 py-2`}
            >
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{signal.label}</p>
              <p className={`mt-1 text-sm font-semibold ${SEVERITY_TEXT[signal.tone]}`}>{signal.value}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Impacto operacional</p>
          <p className="mt-2 text-sm leading-6 text-gray-700">{diagnosis.impact}</p>
        </div>
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Próxima ação</p>
          <p className="mt-2 text-sm leading-6 text-gray-700">{diagnosis.action}</p>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Evidências usadas</p>
            <p className="mt-1 text-sm leading-6 text-gray-700">{evidenceSummary}</p>
          </div>
          <p className="rounded-full bg-[var(--color-surface-subtle)] px-3 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
            Plano de investigação
          </p>
        </div>

        <ol aria-label="Plano técnico de investigação" className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
          {playbook.map((step, index) => (
            <li key={step.title} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-3">
              <div className="flex items-center gap-2">
                <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${SEVERITY_BG[diagnosis.tone]} ${SEVERITY_TEXT[diagnosis.tone]}`}>
                  {index + 1}
                </span>
                <p className="text-sm font-semibold text-[var(--color-text)]">{step.title}</p>
              </div>
              <p className="mt-2 text-xs leading-5 text-[var(--color-text-secondary)]">{step.detail}</p>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  )
}
