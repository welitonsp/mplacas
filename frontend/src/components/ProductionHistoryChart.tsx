import { useState, type KeyboardEvent } from 'react'
import type { AnomalyDailyPoint } from '../lib/dashboard/contracts'
import { clampPercent, formatNumber, formatShortDate, toNumber } from '../lib/format'
import {
  ANOMALY_LEGEND,
  LEVEL_LABEL,
  SEVERITY_BAR,
  SEVERITY_DOT,
  SEVERITY_TEXT,
  levelSeverity,
  performanceSeverity,
} from '../lib/dashboard/visuals'
import { computeYieldStats } from '../lib/dashboard/yield'
import { Card } from './Card'

export function ProductionHistoryChart({
  daily,
  currentStreakDays,
  expectedAvailable = true,
}: {
  daily: AnomalyDailyPoint[]
  currentStreakDays: number
  // `false` quando o baseline sazonal ainda não existe para a usina (ADR-065/068
  // — `expectedProduction.available === false` em `/photovoltaic/summary`). O
  // gráfico de produção real continua útil mesmo assim: só a linha/legenda de
  // "Esperado" some, sem impedir o card inteiro de montar (ver
  // `ProductionHistorySection`).
  expectedAvailable?: boolean
}) {
  // Dia selecionado. `null` = último dia (padrão inicial). Uma vez que o
  // usuário selecione um dia explicitamente (mouse, teclado), o painel de
  // detalhe permanece nele — não reseta em `mouseleave`/`blur`, que fazia o
  // painel parecer instável ao passar o mouse pelo gráfico.
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

  if (daily.length === 0) {
    return (
      <Card>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Histórico de produção diária
        </p>
        <p className="mt-4 text-sm text-gray-500">
          Ainda não há dados diários suficientes para este gráfico.
        </p>
      </Card>
    )
  }

  const maxValue =
    Math.max(
      ...daily.map((d) => {
        const actual = toNumber(d.actual_production_kwh) ?? 0
        const expected = expectedAvailable ? (toNumber(d.expected_production_kwh) ?? 0) : 0
        return Math.max(actual, expected)
      }),
      1
    ) * 1.1

  // Só existe algo pra desenhar como linha de "Esperado" quando o baseline
  // está disponível E ao menos um dia do período tem valor não-nulo — mesmo
  // tratamento de lacuna já usado para irradiância (`hasIrradiation` abaixo).
  const hasExpected =
    expectedAvailable && daily.some((d) => toNumber(d.expected_production_kwh) != null)

  // Polilinha SVG contínua da produção esperada, na mesma escala (0–maxValue)
  // das barras de produção real — ao contrário do traço tracejado por barra
  // anterior, que virava ruído pontilhado em vez de uma linha de referência
  // legível (ver diagnóstico do architect). Segue o mesmo padrão de
  // `buildIrradiationPath` abaixo: `M`/`L` por ponto, reinicia o traço (`M`)
  // quando encontra um dia sem valor em vez de interpolar sobre a lacuna.
  function buildExpectedPath(): string {
    let d = ''
    let drawing = false
    daily.forEach((day, i) => {
      const v = toNumber(day.expected_production_kwh)
      if (v == null) {
        drawing = false
        return
      }
      const x = i + 0.5
      const y = 100 - clampPercent((v / maxValue) * 100)
      d += `${drawing ? 'L' : 'M'}${x} ${y} `
      drawing = true
    })
    return d.trim()
  }

  // % de desempenho do período: soma do real dividido pela soma do esperado no
  // conjunto de dias exibido — derivado do array `daily` já em mãos, sem cálculo
  // novo no backend (ver instrução da tarefa).
  const totalActual = daily.reduce((sum, d) => sum + (toNumber(d.actual_production_kwh) ?? 0), 0)
  const totalExpected = daily.reduce((sum, d) => sum + (toNumber(d.expected_production_kwh) ?? 0), 0)
  const performancePercent = totalExpected > 0 ? (totalActual / totalExpected) * 100 : null

  const activeIndex = selectedIndex ?? daily.length - 1
  const activeDay = daily[activeIndex]
  const activeSeverity = levelSeverity(activeDay.level)

  function moveSelection(delta: number) {
    const next = Math.min(daily.length - 1, Math.max(0, activeIndex + delta))
    setSelectedIndex(next)
  }

  function handleChartKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      moveSelection(1)
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      moveSelection(-1)
    } else if (event.key === 'Home') {
      event.preventDefault()
      setSelectedIndex(0)
    } else if (event.key === 'End') {
      event.preventDefault()
      setSelectedIndex(daily.length - 1)
    }
  }

  // Irradiância só vem preenchida quando a usina tem coordenadas configuradas
  // (coleta Open-Meteo ativa). Overlay e legenda somem por completo quando o
  // dado não existe — sem quebrar o gráfico de produção que já funcionava.
  const irradiationValues = daily.map((d) => toNumber(d.irradiation_kwh_m2))
  const hasIrradiation = irradiationValues.some((v) => v != null)
  const maxIrradiationScale = hasIrradiation
    ? Math.max(...irradiationValues.filter((v): v is number => v != null), 0.1) * 1.15
    : 0

  // Escala própria (0–maxIrradiationScale) desenhada como polilinha num eixo
  // Y independente do das barras de produção — kWh e kWh/m² são grandezas
  // diferentes, não dá pra comparar magnitude num eixo único (ver skill dataviz).
  function buildIrradiationPath(): string {
    let d = ''
    let drawing = false
    irradiationValues.forEach((v, i) => {
      if (v == null) {
        drawing = false
        return
      }
      const x = i + 0.5
      const y = 100 - clampPercent((v / maxIrradiationScale) * 100)
      d += `${drawing ? 'L' : 'M'}${x} ${y} `
      drawing = true
    })
    return d.trim()
  }

  const yieldStats = computeYieldStats(daily)
  const activeIrradiation = toNumber(activeDay.irradiation_kwh_m2)
  const activeYieldInfo = yieldStats.days.find((d) => d.date === activeDay.date) ?? null

  return (
    // `interactive`: as barras do gráfico respondem a clique/foco (seleção do
    // dia ativo abaixo) — o hover do card sinaliza essa interatividade, ao
    // contrário dos cards de métrica só-leitura ao redor.
    <Card interactive>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Histórico de produção diária ({daily.length} dias)
          </p>
          {performancePercent != null && (
            <span
              className={`text-lg font-semibold tabular-nums ${SEVERITY_TEXT[performanceSeverity(performancePercent)]}`}
            >
              Desempenho: {formatNumber(performancePercent, 1)}%
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
          {ANOMALY_LEGEND.map((item) => (
            <span key={item.level} className="inline-flex items-center gap-1">
              <span className={`h-2 w-2 rounded-full ${SEVERITY_DOT[levelSeverity(item.level)]}`} />
              {item.label}
            </span>
          ))}
          {hasExpected && (
            <span className="inline-flex items-center gap-1">
              <span className="h-0 w-3 border-t border-dashed border-[var(--color-chart-reference)]" />
              Esperado
            </span>
          )}
          {hasIrradiation && (
            <span className="inline-flex items-center gap-1">
              <span className="h-0 w-3 border-t-2 border-[var(--color-data-secondary)]" />
              Irradiância solar — eixo à direita, kWh/m²
            </span>
          )}
        </div>
      </div>

      {currentStreakDays > 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-[var(--color-danger)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-danger)]" />
          {currentStreakDays} dia{currentStreakDays > 1 ? 's' : ''} seguido{currentStreakDays > 1 ? 's' : ''} com
          produção abaixo do esperado.
        </p>
      )}

      <div className="mt-4 flex items-stretch gap-2">
        {/* Eixo Y da grandeza principal (kWh de produção) — fora do container
            que rola horizontalmente, pra permanecer visível independente do
            scroll. Reaproveita `maxValue` já calculado acima em vez de criar
            uma segunda escala (ver diagnóstico do architect: sem isto as
            barras não liam como gráfico de verdade). */}
        <div
          className="flex flex-shrink-0 flex-col justify-between py-0 text-right text-xs text-gray-500 tabular-nums"
          style={{ height: '220px' }}
          aria-hidden="true"
        >
          <span>{`${formatNumber(maxValue, 0)} kWh`}</span>
          <span>{`${formatNumber(maxValue / 2, 0)} kWh`}</span>
          <span>0 kWh</span>
        </div>

        <div className="min-w-0 flex-1 overflow-x-auto">
          <div className="relative" style={{ minWidth: `${daily.length * 8}px` }}>
            {hasIrradiation && (
              <span className="pointer-events-none absolute right-0 top-0 z-10 text-xs font-medium text-[var(--color-data-secondary)] tabular-nums">
                {formatNumber(maxIrradiationScale, 1)} kWh/m²
              </span>
            )}

            {/* Área das barras + gridlines + polilinhas de referência, todas
                na mesma altura (220px) — mantém as escalas alinhadas ao pixel
                em vez de esticar um SVG sobre uma área que inclui a régua de
                datas abaixo. */}
            <div className="relative" style={{ height: '220px' }}>
              {/* 3 gridlines horizontais (0, max/2, max) para a grandeza
                  principal — sem elas as barras não têm referência de leitura. */}
              <span className="pointer-events-none absolute inset-x-0 top-0 border-t border-gray-100" />
              <span className="pointer-events-none absolute inset-x-0 border-t border-gray-100" style={{ top: '50%' }} />
              <span className="pointer-events-none absolute inset-x-0 bottom-0 border-t border-gray-100" />

              {hasExpected && (
                <svg
                  className="pointer-events-none absolute inset-0 h-full w-full"
                  viewBox={`0 0 ${daily.length} 100`}
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  <path
                    d={buildExpectedPath()}
                    fill="none"
                    stroke="var(--color-chart-reference)"
                    strokeWidth="1.5"
                    strokeDasharray="4 3"
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
              )}

              {hasIrradiation && (
                <svg
                  className="pointer-events-none absolute inset-0 h-full w-full"
                  viewBox={`0 0 ${daily.length} 100`}
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  <path
                    d={buildIrradiationPath()}
                    fill="none"
                    stroke="var(--color-data-secondary)"
                    strokeWidth="1.5"
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
              )}

              {/* Único tab stop para todo o gráfico — navegação entre dias é
                  por seta esquerda/direita (ver `handleChartKeyDown`), não por
                  Tab atravessando até 90 barras. */}
              <div
                className="flex h-full items-end gap-[2px] rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
                tabIndex={0}
                role="slider"
                aria-label="Histórico de produção diária. Use as setas esquerda e direita para navegar entre os dias."
                aria-valuemin={0}
                aria-valuemax={daily.length - 1}
                aria-valuenow={activeIndex}
                aria-valuetext={`${formatShortDate(activeDay.date)}: ${formatNumber(
                  toNumber(activeDay.actual_production_kwh) ?? 0
                )} kWh produzidos de ${formatNumber(
                  toNumber(activeDay.expected_production_kwh) ?? 0
                )} kWh esperados. Nível: ${LEVEL_LABEL[activeDay.level]}.`}
                onKeyDown={handleChartKeyDown}
              >
                {daily.map((d, i) => {
                  const actual = toNumber(d.actual_production_kwh) ?? 0
                  const barHeightPercent = clampPercent((actual / maxValue) * 100)
                  const severity = levelSeverity(d.level)
                  const isActive = activeIndex === i

                  return (
                    <div
                      key={d.date}
                      className="relative flex h-full flex-1 items-end rounded-sm"
                      style={{ minWidth: '6px' }}
                      onMouseEnter={() => setSelectedIndex(i)}
                      onClick={() => setSelectedIndex(i)}
                    >
                      <span
                        className={`w-full rounded-t-sm ${SEVERITY_BAR[severity]} ${
                          isActive ? '' : 'opacity-90'
                        }`}
                        style={{ height: `${Math.max(barHeightPercent, 2)}%` }}
                      />
                    </div>
                  )
                })}
              </div>

              {hasIrradiation && (
                <span className="pointer-events-none absolute right-0 bottom-0 z-10 text-xs font-medium text-[var(--color-data-secondary)] tabular-nums">
                  0 kWh/m²
                </span>
              )}
            </div>

            {/* Régua de datas DENTRO do mesmo container com `overflow-x-auto` e
                `minWidth` das barras acima (ver P1-05) — assim ela rola junto
                com o gráfico e os rótulos sempre correspondem às barras reais,
                mesmo em telas menores que a largura mínima do gráfico. */}
            <div className="mt-1 flex justify-between text-xs text-gray-500 tabular-nums">
              <span>{formatShortDate(daily[0].date)}</span>
              <span>{formatShortDate(daily[Math.floor(daily.length / 2)].date)}</span>
              <span>{formatShortDate(daily[daily.length - 1].date)}</span>
            </div>
          </div>
        </div>
      </div>

      <div
        className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-gray-100 bg-gray-50 p-3 text-xs text-gray-600"
        aria-live="polite"
      >
        <span className="font-medium text-gray-900">{formatShortDate(activeDay.date)}</span>
        <span>
          Real:{' '}
          <strong className="text-gray-900 tabular-nums">
            {formatNumber(activeDay.actual_production_kwh)} kWh
          </strong>
        </span>
        <span>
          Esperado:{' '}
          <strong className="text-gray-900 tabular-nums">
            {formatNumber(activeDay.expected_production_kwh)} kWh
          </strong>
        </span>
        {activeDay.deviation_percent != null && (
          <span className={`tabular-nums ${SEVERITY_TEXT[activeSeverity]}`}>
            Desvio: {formatNumber(activeDay.deviation_percent, 1)}%
          </span>
        )}
        <span className={`inline-flex items-center gap-1 font-medium ${SEVERITY_TEXT[activeSeverity]}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${SEVERITY_DOT[activeSeverity]}`} />
          {LEVEL_LABEL[activeDay.level]}
        </span>
        {activeIrradiation != null && (
          <span>
            Irradiância:{' '}
            <strong className="text-[var(--color-data-secondary)] tabular-nums">
              {formatNumber(activeIrradiation, 2)} kWh/m²
            </strong>
          </span>
        )}
        {activeYieldInfo && (
          <span>
            Rendimento:{' '}
            <strong className="text-[var(--color-data-secondary)] tabular-nums">
              {formatNumber(activeYieldInfo.yieldValue, 2)} kWh por kWh/m²
            </strong>{' '}
            <span className="text-gray-500 tabular-nums">
              ({activeYieldInfo.deviationPercent > 0 ? '+' : ''}
              {formatNumber(activeYieldInfo.deviationPercent, 0)}% vs. média do período)
            </span>
          </span>
        )}
      </div>
    </Card>
  )
}
