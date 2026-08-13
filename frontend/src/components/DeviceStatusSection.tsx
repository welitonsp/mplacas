import type { DeviceDailyStatus, DeviceDailyStatusResponse } from '../lib/dashboard/device-contracts'
import {
  observationDateUnavailableMessage,
  yieldUnavailableMessage,
} from '../lib/dashboard/device-contracts'
import type { PlantResource } from '../hooks/usePlantResource'
import type { Severity } from '../lib/dashboard/contracts'
import { SEVERITY_TEXT } from '../lib/dashboard/visuals'
import { formatFullDate, formatNumber, toNumber } from '../lib/format'
import { Card } from './Card'
import { RetryableError } from './RetryableError'
import { SectionTitle } from './SectionTitle'

// "Visão por inversor" (ADR-074, Decisão 5) — drill-down do agregado
// "Disponibilidade dos dados" (`TechnicalPage.tsx`, tile "Disponibilidade dos
// dados"/`ReportingAvailabilityCard`): aquele número responde "quanto",
// esta seção responde "qual". Recurso próprio (`GET /devices/daily-status`,
// `usePlantResource` isolado — ADR-072, Decisão 3), então uma falha aqui
// nunca apaga PR/perdas/degradação renderizados por
// `TechnicalPerformanceSection` ao lado.
//
// Escala real ~2 inversores por usina (ADR-074, Restrição 4) — grade de 2
// colunas, sem paginação/busca/filtro/virtualização.
export function DeviceStatusSection({
  resource,
}: {
  resource: PlantResource<DeviceDailyStatusResponse>
}) {
  return (
    <div>
      <SectionTitle as="h2">Inversores</SectionTitle>
      <div role="region" aria-label="Inversores">
        {resource.error ? (
          <RetryableError message={resource.error} onRetry={resource.refetch} />
        ) : resource.data === null ? (
          <DeviceStatusSkeleton />
        ) : (
          <DeviceStatusList status={resource.data} />
        )}
      </div>
    </div>
  )
}

function DeviceStatusSkeleton() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Carregando inversores"
      className="grid grid-cols-1 gap-3 sm:grid-cols-2"
    >
      <span className="sr-only">Carregando inversores</span>
      {[0, 1].map((key) => (
        <Card key={key} className="animate-pulse">
          <div className="h-3 w-16 rounded-full bg-gray-200" />
          <div className="mt-2 h-5 w-32 rounded bg-gray-200" />
          <div className="mt-4 h-6 w-28 rounded-full bg-gray-100" />
        </Card>
      ))}
    </div>
  )
}

function DeviceStatusList({ status }: { status: DeviceDailyStatusResponse }) {
  return (
    <>
      <p className="mb-3 text-xs text-gray-500">
        {status.observation_date !== null
          ? `Leitura de ${formatFullDate(status.observation_date)}.`
          : observationDateUnavailableMessage(
              status.observation_date_unavailable_reason ?? 'NO_PRODUCTION_HISTORY'
            )}
      </p>

      {status.devices.length === 0 ? (
        <Card>
          <p className="text-sm text-gray-600">Nenhum inversor cadastrado nesta usina ainda.</p>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {status.devices.map((device) => (
              <DeviceCard key={device.device_id} device={device} />
            ))}
          </div>
          <p className="mt-3 text-xs text-gray-500">
            Cada inversor é comparado só com o histórico dele mesmo — nunca com outro inversor.
          </p>
        </>
      )}
    </>
  )
}

interface YieldMeta {
  severity: Severity
  label: string
  detail: string
}

// Formata o desvio percentual JÁ CALCULADO pelo backend
// (`relative_to_own_median_deviation_percent` — ADR-074, Restrição 7 / regra
// 6 da tarefa) em texto de UI. Nenhuma conta acontece aqui, só arredondamento
// e escolha de sinal/texto — e nessa ordem: arredonda primeiro, decide o
// sinal a partir do valor JÁ arredondado (correção P1, revisão de T1c,
// 2026-08-12). Decidir o sinal a partir do valor bruto produzia "−0%" para
// `-0.4` e "+0%" para `0.4` — a faixa MAIS COMUM de um inversor saudável
// (desvio quase nulo contra a própria mediana), então esse absurdo
// tipográfico aparecia justo no caso normal. `rounded === 0` também cobre o
// zero negativo que `Math.round` produz para valores em (-1, 0): `-0 === 0`
// é `true` em JavaScript, então a checagem captura os dois.
function relativeToMedianText(deviationPercent: string | null): string | null {
  const numeric = toNumber(deviationPercent)
  if (numeric === null) return null
  const rounded = Math.round(numeric)
  if (rounded === 0) return 'Em linha com a mediana deste inversor.'
  const sign = rounded > 0 ? '+' : ''
  return `${sign}${formatNumber(rounded, 0)}% em relação à mediana deste inversor.`
}

// Deriva rótulo/tom/detalhe SOMENTE do que o backend já decidiu
// (`yield_status`/`yield_unavailable_reason`) — nenhuma comparação, limiar ou
// razão é recalculada aqui (ADR-074, Restrição 7 / regra 6 da tarefa).
// `UNKNOWN` nunca cai no ramo `NORMAL` (a "armadilha obrigatória" do ADR):
// os três ramos abaixo são mutuamente exclusivos por construção do `switch`.
function yieldMeta(device: DeviceDailyStatus): YieldMeta {
  const relativeText = relativeToMedianText(device.relative_to_own_median_deviation_percent)

  switch (device.yield_status) {
    case 'NORMAL':
      return {
        severity: 'success',
        label: 'Rendimento normal',
        detail: relativeText ?? 'Dentro da faixa esperada para este inversor.',
      }
    case 'DROPPED':
      return {
        severity: 'danger',
        label: 'Queda de rendimento',
        detail: relativeText ?? 'Abaixo da faixa esperada para este inversor.',
      }
    case 'UNKNOWN':
      return {
        severity: 'neutral',
        label: 'Sem avaliação de rendimento',
        detail:
          device.yield_unavailable_reason !== null
            ? yieldUnavailableMessage(device.yield_unavailable_reason)
            : 'Motivo não informado pelo backend.',
      }
  }
}

function DeviceCard({ device }: { device: DeviceDailyStatus }) {
  // "Não reportou" nunca é 0 nem "—" — estado nomeado com ícone + texto + cor
  // (ADR-074, Decisão 5, regra 2). Vocabulário travado: "não reportou", nunca
  // "offline"/"uptime"/"fora do ar" — o backend só observa ausência de linha
  // em `daily_energy`, não sabe distinguir a causa (mesma disciplina de
  // `ReportingAvailabilityCard.tsx`).
  if (device.reporting_status === 'NOT_REPORTED') {
    return (
      <Card accent="warning">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Inversor</p>
        <p className="mt-1 text-base font-semibold text-gray-950 break-all">{device.serial_number}</p>
        <div className="mt-3 flex items-center gap-2">
          <StatusIcon tone="warning" />
          <span className={`text-sm font-semibold ${SEVERITY_TEXT.warning}`}>Não reportou</span>
        </div>
        <p className="mt-2 text-xs leading-5 text-gray-600">
          {device.last_reported_date !== null
            ? `Última leitura registrada: ${formatFullDate(device.last_reported_date)}.`
            : 'Nunca reportou dado nesta usina.'}
        </p>
      </Card>
    )
  }

  const productionKwh = toNumber(device.production_kwh)
  const meta = yieldMeta(device)

  return (
    <Card accent={meta.severity}>
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Inversor</p>
      <p className="mt-1 text-base font-semibold text-gray-950 break-all">{device.serial_number}</p>
      {/* Um inversor que reportou exatamente 0 kWh mostra "0 kWh" — visualmente
          distinto do bloco "Não reportou" acima (unidade sempre visível, nunca
          um "—" no lugar de um zero real). */}
      <p className="mt-2 text-xl font-semibold text-gray-900 tabular-nums">
        {productionKwh === null ? '—' : `${formatNumber(productionKwh)} kWh`}
      </p>
      <div className="mt-2 flex items-center gap-2">
        <StatusIcon tone={meta.severity} />
        <span className={`text-sm font-semibold ${SEVERITY_TEXT[meta.severity]}`}>{meta.label}</span>
      </div>
      <p className="mt-1 text-xs leading-5 text-gray-600">{meta.detail}</p>
    </Card>
  )
}

// Ícone próprio por severidade (forma, não só cor) — 4 silhuetas distintas
// (check / triângulo de aviso / círculo de alerta / interrogação), decorativo
// (`aria-hidden`): o texto ao lado já carrega o significado para leitor de
// tela.
function StatusIcon({ tone }: { tone: Severity }) {
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
