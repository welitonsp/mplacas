import { useState, type KeyboardEvent } from 'react'
import type { AnomalyDailyPoint } from '../lib/dashboard/contracts'
import { clampPercent, formatNumber, formatShortDate, toNumber } from '../lib/format'
import { averageActualProduction } from '../lib/dashboard/production-alerts'
import {
  ANOMALY_LEGEND,
  SEVERITY_BAR,
  SEVERITY_DOT,
  SEVERITY_TEXT,
  levelLabel,
  levelSeverity,
  performanceSeverity,
} from '../lib/dashboard/visuals'
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
  // referência esperada (baseline sazonal) some, sem impedir o card inteiro de
  // montar (ver `ProductionHistorySection`).
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
  const actualProductionValues = daily
    .map((day) => toNumber(day.actual_production_kwh))
    .filter((value): value is number => value != null)
  const showInlineDateLabels = daily.length <= 7
  const productionDays = daily
    .map((day) => ({ day, actual: toNumber(day.actual_production_kwh) }))
    .filter((item): item is { day: AnomalyDailyPoint; actual: number } => item.actual != null)
  const productionReadout =
    productionDays.length === 0
      ? null
      : productionDays.reduce(
          (acc, item) => ({
            total: acc.total + item.actual,
            best: item.actual > acc.best.actual ? item : acc.best,
            worst: item.actual < acc.worst.actual ? item : acc.worst,
          }),
          { total: 0, best: productionDays[0], worst: productionDays[0] }
        )
  // Rotulado "janela exibida" (não "período") na legenda/painel de detalhe
  // abaixo — `daily` aqui é o recorte visível escolhido no seletor de
  // período da tela (7/30/90 dias, ver `ProductionHistorySection`), que é
  // menor que a janela completa que o backend analisou para o rendimento
  // (`YieldCard`, ao lado). As duas usavam a mesma palavra "período" para
  // janelas diferentes, o que fazia parecer o mesmo número (plano T7b, P1
  // "dois período diferentes na mesma viewport") — agora só `YieldCard`
  // usa "período/janela analisada" para a janela cheia do backend.
  const averageProduction = averageActualProduction(daily).average
  const averageLineY = averageProduction == null ? null : 100 - clampPercent((averageProduction / maxValue) * 100)
  const belowAverageDays =
    averageProduction == null ? null : actualProductionValues.filter((value) => value < averageProduction).length

  // `expected_production_kwh` é o MESMO valor escalar replicado pelo backend
  // em todos os dias do período (baseline sazonal do período; não uma
  // expectativa calculada por dia — ver `anomaly_service.py:145-171`, onde
  // `expected_daily_production_kwh` é um parâmetro único atribuído sem
  // variação dentro do laço `for current_day in ...`). Por isso a referência
  // visual é UMA linha horizontal única (mesmo padrão de `averageLineY`
  // abaixo), não mais uma polilinha ponto a ponto: desenhar ponto a ponto
  // sugeria uma variação diária que não existe no dado. Qualquer dia com
  // valor não-nulo serve pra achar a altura da linha — é sempre o mesmo
  // número, não uma escolha entre valores diferentes.
  const expectedDailyValue = expectedAvailable
    ? (daily.map((d) => toNumber(d.expected_production_kwh)).find((v): v is number => v != null) ?? null)
    : null
  const hasExpected = expectedDailyValue != null
  const expectedLineY = hasExpected ? 100 - clampPercent((expectedDailyValue / maxValue) * 100) : null

  // % de desempenho do período: soma do real dividido pela soma do esperado no
  // conjunto de dias exibido — derivado do array `daily` já em mãos, sem cálculo
  // novo no backend (ver instrução da tarefa). Soma só os dias em que AMBOS
  // real e esperado existem — somar `0` para um dia sem expectativa (`?? 0`)
  // produziria um "esperado total" falso menor que o real, distorcendo o
  // percentual pra cima sem nenhum dado a mais (ver diagnóstico do architect).
  const { totalActual, totalExpected } = daily.reduce(
    (acc, d) => {
      const actual = toNumber(d.actual_production_kwh)
      const expected = toNumber(d.expected_production_kwh)
      if (actual == null || expected == null) return acc
      return { totalActual: acc.totalActual + actual, totalExpected: acc.totalExpected + expected }
    },
    { totalActual: 0, totalExpected: 0 }
  )
  const performancePercent = totalExpected > 0 ? (totalActual / totalExpected) * 100 : null

  // Pelo menos um dia sem expectativa disponível (`level: null`) — as barras
  // desses dias renderizam em tom neutro (ver `levelSeverity`); a legenda
  // ganha uma entrada explícita pra essa cor não aparecer sem explicação
  // (regra de acessibilidade: cor nunca sozinha, sempre com rótulo).
  const hasUnassessedDay = daily.some((d) => d.level === null)

  const activeIndex = selectedIndex ?? daily.length - 1
  const activeDay = daily[activeIndex]
  const activeSeverity = levelSeverity(activeDay.level)
  const activeActual = toNumber(activeDay.actual_production_kwh)
  const activeAverageDeltaPercent =
    activeActual != null && averageProduction != null && averageProduction > 0
      ? ((activeActual - averageProduction) / averageProduction) * 100
      : null
  const activeAverageDeltaTone =
    activeAverageDeltaPercent == null
      ? 'text-gray-500'
      : activeAverageDeltaPercent < -15
        ? SEVERITY_TEXT.danger
        : activeAverageDeltaPercent < 0
          ? SEVERITY_TEXT.warning
          : SEVERITY_TEXT.success

  // Texto acessível do dia ativo: quando `expected_production_kwh` é `null`
  // (sem expectativa disponível pra esse dia), a frase NÃO pode dizer "0 kWh
  // esperados" nem citar um nível — isso fabricaria um valor e uma severidade
  // que o backend explicitamente não calculou (ver `AnomalyDailyPoint.level`).
  // Quando o valor existe, a frase diz "baseline esperado do período", nunca
  // "esperado hoje": é o mesmo escalar replicado em todos os dias do recorte
  // (ver comentário de `expectedDailyValue` acima), não uma previsão deste
  // dia específico.
  function buildDayValueText(day: AnomalyDailyPoint): string {
    const actualText = `${formatNumber(toNumber(day.actual_production_kwh) ?? 0)} kWh produzidos`
    const expected = toNumber(day.expected_production_kwh)
    if (expected == null || day.level === null) return `${formatShortDate(day.date)}: ${actualText}.`
    return `${formatShortDate(day.date)}: ${actualText}. Baseline esperado do período: ${formatNumber(
      expected
    )} kWh/dia. Nível: ${levelLabel(day.level)}.`
  }

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

  const activeIrradiation = toNumber(activeDay.irradiation_kwh_m2)
  // Rendimento e desvio já prontos do backend (`yield_kwh_per_kwh_m2`/
  // `yield_deviation_from_period_percent`, ver `intelligence/anomaly_service.py::
  // _compute_period_yield` — 2026-08-13, plano T7). `null` quando o dia não
  // tem produção/irradiância positivas ao mesmo tempo, ou quando nenhum dia
  // do período analisado qualifica — nunca recalculado aqui (ver
  // `no-client-computed-yield-deviation.test.ts`).
  const activeYieldValue = toNumber(activeDay.yield_kwh_per_kwh_m2)
  const activeYieldDeviationPercent = toNumber(activeDay.yield_deviation_from_period_percent)

  return (
    // `interactive`: as barras do gráfico respondem a clique/foco (seleção do
    // dia ativo abaixo) — o hover do card sinaliza essa interatividade, ao
    // contrário dos cards de métrica só-leitura ao redor.
    <Card interactive className="overflow-hidden">
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
          {belowAverageDays != null && (
            <span className="text-sm font-semibold text-gray-700 tabular-nums">
              {belowAverageDays} {belowAverageDays === 1 ? 'dia' : 'dias'} abaixo da média
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
          {ANOMALY_LEGEND.map((item) => (
            <span
              key={item.level}
              className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 shadow-sm"
            >
              <span className={`h-2 w-2 rounded-full ${SEVERITY_DOT[levelSeverity(item.level)]}`} />
              {item.label}
            </span>
          ))}
          {hasUnassessedDay && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 shadow-sm">
              <span className={`h-2 w-2 rounded-full ${SEVERITY_DOT.neutral}`} />
              Sem expectativa
            </span>
          )}
          {hasExpected && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 shadow-sm">
              <span className="h-0 w-3 border-t border-dashed border-[var(--color-chart-reference)]" />
              Média diária esperada (baseline sazonal)
            </span>
          )}
          {averageProduction != null && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 shadow-sm">
              <span className="h-0 w-3 border-t-2 border-[var(--color-brand-primary)]" />
              Média da janela exibida
            </span>
          )}
          {hasIrradiation && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 shadow-sm">
              <span className="h-0 w-3 border-t-2 border-[var(--color-data-secondary)]" />
              Irradiância solar — eixo à direita, kWh/m²
            </span>
          )}
        </div>
      </div>

      {productionReadout != null && (
        <div
          data-testid="production-period-readout"
          className="mt-4 grid gap-2 sm:grid-cols-3"
          aria-label="Resumo executivo do período de produção"
        >
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-3 py-2.5">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">
              Total produzido
            </p>
            <p className="mt-1 text-lg font-semibold text-gray-950 tabular-nums">
              {formatNumber(productionReadout.total, 1)} kWh
            </p>
            <p className="mt-0.5 text-xs text-gray-500">
              {productionDays.length} {productionDays.length === 1 ? 'dia com dado' : 'dias com dado'}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--color-success)]/20 bg-[var(--color-success-light)] px-3 py-2.5">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-success-text)]/80">
              Melhor dia
            </p>
            <p className="mt-1 text-lg font-semibold text-[var(--color-success-text)] tabular-nums">
              {formatNumber(productionReadout.best.actual, 1)} kWh
            </p>
            <p className="mt-0.5 text-xs font-medium text-[var(--color-success-text)]/80 tabular-nums">
              em {formatShortDate(productionReadout.best.day.date)}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--color-warning)]/25 bg-[var(--color-warning-light)] px-3 py-2.5">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-warning-text)]/80">
              Pior dia
            </p>
            <p className="mt-1 text-lg font-semibold text-[var(--color-warning-text)] tabular-nums">
              {formatNumber(productionReadout.worst.actual, 1)} kWh
            </p>
            <p className="mt-0.5 text-xs font-medium text-[var(--color-warning-text)]/80 tabular-nums">
              em {formatShortDate(productionReadout.worst.day.date)}
            </p>
          </div>
        </div>
      )}

      {currentStreakDays > 0 && (
        <p className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-[var(--color-danger)]/20 bg-[var(--color-danger-light)] px-3 py-1.5 text-xs font-semibold text-[var(--color-danger-text)] shadow-sm">
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
            <div
              className="relative rounded-2xl border border-[var(--color-border)] bg-[linear-gradient(180deg,var(--color-surface)_0%,var(--color-surface-subtle)_100%)] shadow-inner"
              style={{ height: '220px' }}
            >
              {/* 3 gridlines horizontais (0, max/2, max) para a grandeza
                  principal — sem elas as barras não têm referência de leitura. */}
              <span className="pointer-events-none absolute inset-x-0 top-0 border-t border-gray-100" />
              <span className="pointer-events-none absolute inset-x-0 border-t border-gray-100" style={{ top: '50%' }} />
              <span className="pointer-events-none absolute inset-x-0 bottom-0 border-t border-gray-100" />

              {averageLineY != null && (
                <svg
                  className="pointer-events-none absolute inset-0 h-full w-full"
                  viewBox={`0 0 ${daily.length} 100`}
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  <line
                    x1="0"
                    x2={daily.length}
                    y1={averageLineY}
                    y2={averageLineY}
                    stroke="var(--color-brand-primary)"
                    strokeWidth="1.6"
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
              )}

              {hasExpected && expectedLineY != null && (
                <svg
                  className="pointer-events-none absolute inset-0 h-full w-full"
                  viewBox={`0 0 ${daily.length} 100`}
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  <line
                    x1="0"
                    x2={daily.length}
                    y1={expectedLineY}
                    y2={expectedLineY}
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
                className="relative z-10 flex h-full items-end gap-[2px] rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
                tabIndex={0}
                role="slider"
                aria-label="Histórico de produção diária. Use as setas esquerda e direita para navegar entre os dias."
                aria-valuemin={0}
                aria-valuemax={daily.length - 1}
                aria-valuenow={activeIndex}
                aria-valuetext={buildDayValueText(activeDay)}
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
                      {showInlineDateLabels && (
                        <span
                          data-testid="production-bar-date-label"
                          aria-hidden="true"
                          className="pointer-events-none absolute left-1/2 z-20 -translate-x-1/2 rounded-full border border-[var(--color-border)] bg-white/95 px-1.5 py-0.5 text-xs font-semibold leading-none text-gray-700 shadow-sm tabular-nums"
                          style={{ bottom: `calc(${Math.max(barHeightPercent, 2)}% + 6px)` }}
                        >
                          {formatShortDate(d.date)}
                        </span>
                      )}
                      <span
                        className={`w-full rounded-t-md shadow-[inset_0_1px_0_rgba(255,255,255,0.28)] transition-all duration-150 ${
                          SEVERITY_BAR[severity]
                        } ${
                          isActive ? 'ring-2 ring-[var(--color-text-primary)] ring-offset-1 ring-offset-[var(--color-surface)]' : 'opacity-85 hover:opacity-100'
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
        className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border border-[var(--color-border)] bg-[linear-gradient(135deg,var(--color-surface)_0%,var(--color-surface-subtle)_100%)] p-3 text-xs text-gray-600 shadow-sm"
        aria-live="polite"
      >
        <span className="inline-flex rounded-full bg-[var(--color-brand-primary-light)] px-2.5 py-1 font-semibold text-[var(--color-brand-primary)]">
          {formatShortDate(activeDay.date)}
        </span>
        <span>
          Real:{' '}
          <strong className="text-gray-900 tabular-nums">
            {formatNumber(activeDay.actual_production_kwh)} kWh
          </strong>
        </span>
        {/* Sem cláusula quando `expected_production_kwh` é `null` (sem
            expectativa disponível pra esse dia) — nunca "0 kWh esperados"
            fabricado, mesmo princípio de `LatestDailyProductionCard` para o
            mesmo caso. Rótulo diz "baseline esperado (período)", não
            "esperado hoje": é o mesmo escalar replicado pelo backend em
            todos os dias do recorte (baseline sazonal do período, ver
            comentário de `expectedDailyValue` acima), não uma previsão
            específica deste dia — daí também o sufixo "kWh/dia" em vez de
            "kWh" (é uma taxa de referência, não o total do dia). */}
        {activeDay.expected_production_kwh != null && (
          <span>
            Baseline esperado (período):{' '}
            <strong className="text-gray-900 tabular-nums">
              {formatNumber(activeDay.expected_production_kwh)} kWh/dia
            </strong>
          </span>
        )}
        {activeDay.deviation_percent != null && (
          <span className={`tabular-nums ${SEVERITY_TEXT[activeSeverity]}`}>
            Desvio: {formatNumber(activeDay.deviation_percent, 1)}%
          </span>
        )}
        {averageProduction != null && (
          <span>
            Média da janela exibida:{' '}
            <strong className="text-[var(--color-brand-primary)] tabular-nums">
              {formatNumber(averageProduction, 1)} kWh/dia
            </strong>
          </span>
        )}
        {activeAverageDeltaPercent != null && (
          <span className={`tabular-nums ${activeAverageDeltaTone}`}>
            Vs. média: {activeAverageDeltaPercent > 0 ? '+' : ''}
            {formatNumber(activeAverageDeltaPercent, 0)}%
          </span>
        )}
        <span className={`inline-flex items-center gap-1 font-medium ${SEVERITY_TEXT[activeSeverity]}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${SEVERITY_DOT[activeSeverity]}`} />
          {levelLabel(activeDay.level)}
        </span>
        {activeIrradiation != null && (
          <span>
            Irradiância:{' '}
            <strong className="text-[var(--color-data-secondary)] tabular-nums">
              {formatNumber(activeIrradiation, 2)} kWh/m²
            </strong>
          </span>
        )}
        {activeYieldValue != null && (
          <span>
            Rendimento:{' '}
            <strong className="text-[var(--color-data-secondary)] tabular-nums">
              {formatNumber(activeYieldValue, 2)} kWh por kWh/m²
            </strong>{' '}
            {activeYieldDeviationPercent != null && (
              <span className="text-gray-500 tabular-nums">
                ({activeYieldDeviationPercent > 0 ? '+' : ''}
                {formatNumber(activeYieldDeviationPercent, 0)}% vs. período analisado)
              </span>
            )}
          </span>
        )}
      </div>
    </Card>
  )
}
