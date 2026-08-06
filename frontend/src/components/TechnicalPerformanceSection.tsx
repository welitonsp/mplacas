import { useState } from 'react'
import type { PhotovoltaicSummaryResponse } from '../lib/dashboard/photovoltaic-contracts'
import { BaselineDegradationCard } from './BaselineDegradationCard'
import { LossBreakdownSection } from './LossBreakdownSection'
import { MetricCardSkeletonGrid } from './MetricCardSkeletonGrid'
import { PerformanceRatioCard } from './PerformanceRatioCard'
import { ReportingAvailabilityCard } from './ReportingAvailabilityCard'
import { SpecificYieldCard } from './SpecificYieldCard'

const CONTENT_ID = 'technical-performance-content'
// Só a preferência de expansão é persistida — nenhum dado de negócio. Padrão
// (decisão de 2026-08-06, revertendo a Onda 3): expandida — os gráficos
// técnicos (PR, disponibilidade, perdas) agora carregam informação visual
// forte o bastante para não ficarem escondidos por padrão. Se o
// `localStorage` estiver indisponível (modo privado, política de origem
// etc.), o padrão continua sendo "expandida" e a interação segue funcionando
// dentro da sessão (ver `readStoredExpanded`/`writeStoredExpanded`).
const STORAGE_KEY = 'mplacas:technical-performance-expanded'

function readStoredExpanded(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== 'false'
  } catch {
    return true
  }
}

function writeStoredExpanded(expanded: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(expanded))
  } catch {
    // Armazenamento indisponível — a preferência simplesmente não persiste
    // entre recarregamentos, o que não impede o uso da página nesta sessão.
  }
}

// Bloco próprio ("Como está o desempenho técnico?"), separado do Bloco 1
// ("Está indo bem?"): PR, yield específico, disponibilidade de reporte,
// degradação e atribuição de causa de perda respondem a mesma pergunta de
// alto nível, mas com granularidade técnica que um dono de usina leigo não
// precisa ver misturada com o resumo executivo — ver decisão da Etapa 6.
// `summary === null` é o estado de carregamento; blocos individuais `null`
// dentro de um `summary` já carregado mostram mensagem específica (Etapa 1
// estendida para performance/losses nesta etapa).
//
// Etapa 3.4: colapsada por padrão (é a camada de maior granularidade técnica
// da página, não a primeira coisa que um dono de usina precisa ver — os
// diagnósticos críticos continuam sempre visíveis fora daqui, em
// `DiagnosticsCard`/`AttentionSummary`, que `DashboardPage` nunca coloca
// dentro desta seção). O conteúdo continua montado no DOM quando colapsado
// (atributo `hidden`, não desmontagem condicional) para não perder estado de
// scroll/foco ao alternar — e para os testes existentes de cada card
// individual (`PerformanceRatioCard.test.tsx` etc.) continuarem
// encontráveis via `container.querySelector`, mesmo que inacessíveis por
// leitor de tela nesse estado (`hidden` remove da árvore de acessibilidade,
// que é exatamente o comportamento pedido: colapsado não conta como
// "acessível", expandido conta).
export function TechnicalPerformanceSection({ summary }: { summary: PhotovoltaicSummaryResponse | null }) {
  const [expanded, setExpanded] = useState<boolean>(readStoredExpanded)

  const toggle = () => {
    setExpanded((prev) => {
      const next = !prev
      writeStoredExpanded(next)
      return next
    })
  }

  return (
    <div>
      {/* O cabeçalho clicável precisa aparecer no outline de headings da
          página (é uma seção de mesmo nível que "Financeiro"/"Retorno do
          investimento" em `DashboardPage`) — o `<button>` sozinho não conta
          como heading para leitores de tela, então o `h2` o envolve sem
          alterar `aria-expanded`/`aria-controls`/comportamento algum. */}
      <h2 className="mb-3">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={expanded}
          aria-controls={CONTENT_ID}
          className="flex w-full items-center justify-between gap-2 rounded text-left text-base font-semibold text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
        >
          <span>Desempenho técnico</span>
          <span className="flex items-center gap-1 text-xs font-medium text-[var(--color-brand-primary)]">
            {expanded ? 'Ocultar desempenho técnico' : 'Ver desempenho técnico'}
            <span aria-hidden="true" className={`transition-transform duration-150 ${expanded ? 'rotate-180' : ''}`}>
              ▾
            </span>
          </span>
        </button>
      </h2>

      <div id={CONTENT_ID} role="region" aria-label="Desempenho técnico" hidden={!expanded}>
        {summary === null ? (
          <MetricCardSkeletonGrid count={4} />
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <PerformanceRatioCard
                performance={summary.performance}
                unavailableReason={summary.performance_unavailable_reason}
              />
              <SpecificYieldCard
                performance={summary.performance}
                unavailableReason={summary.performance_unavailable_reason}
              />
              <ReportingAvailabilityCard
                performance={summary.performance}
                unavailableReason={summary.performance_unavailable_reason}
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <BaselineDegradationCard
                baseline={summary.baseline}
                unavailableReason={summary.baseline_unavailable_reason}
                referenceCompleteOn={summary.reference_complete_on}
              />
              <LossBreakdownSection losses={summary.losses} unavailableReason={summary.losses_unavailable_reason} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
