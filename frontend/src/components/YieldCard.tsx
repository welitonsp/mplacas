import type { AnomalyDailyPoint, MetricValue } from '../lib/dashboard/contracts'
import { formatNumber, formatShortDate, toNumber } from '../lib/format'
import { Card } from './Card'

// Rendimento = produção real (kWh) / irradiância (kWh/m²) — kWh gerados por
// cada kWh/m² de sol recebido. É a métrica que separa "problema na usina" de
// "estava nublado": produção baixa com irradiância baixa é dia nublado
// (normal), produção baixa com irradiância alta é problema real.
//
// Movido do frontend para o backend (2026-08-13, plano T7):
// `yield_kwh_per_kwh_m2`/`yield_deviation_from_period_percent` por dia e
// `period_yield_kwh_per_kwh_m2`/`yield_atypical_threshold_percent` do
// período já vêm prontos de `GET /energy/anomalies/latest`
// (`intelligence/anomaly_service.py::_compute_period_yield`/
// `_yield_deviation_from_period_percent`) — este componente só lê e formata,
// nunca soma/divide/reescala valores entre si (ver
// `no-client-computed-yield-deviation.test.ts`, a guarda estática que impede
// a reintrodução do cálculo aqui).
//
// `daily` PRECISA ser a janela completa que o backend analisou (hoje até 90
// dias, ver `lib/api.ts::fetchAnomalyHistory`), nunca um recorte visível
// menor (ex.: os 7/30 dias que o seletor de período da tela mostra) —
// corrigido no plano T7b, P0 ("o card afirma o que não verificou"):
// `periodYieldKwhPerKwhM2` e o desvio de cada dia já vêm calculados pelo
// backend sobre essa mesma janela cheia, então varrer aqui só um recorte
// menor faria o card dizer "estável" tendo checado uma fatia do que o
// cabeçalho anuncia — e faria a lista de dias atípicos aparecer/sumir ao
// trocar o recorte da tela sem o cabeçalho mudar (ver `ProductionHistorySection`,
// que passa `anomalyState.data.daily` inteiro para este componente, nunca o
// recorte filtrado usado pelo gráfico ao lado).
//
// `periodYieldKwhPerKwhM2`/`yieldAtypicalThresholdPercent`/
// `periodYieldSampleDays` vêm do envelope da resposta
// (`AnomalyDashboardResponse`), não de cada item de `daily` — por isso são
// props próprias, não campos lidos de dentro de `daily[i]`.
// `periodYieldSampleDays` (nunca `daysAnalyzed`/`days_analyzed`) rotula o
// cabeçalho com quantos dias realmente entraram no cálculo do rendimento
// agregado (produção E irradiância positivas nesse dia) — um número menor ou
// igual ao total de dias com produção persistida, e propositalmente
// diferente dele quando algum dia não tem irradiância (plano T7b, P1 "o
// rótulo usa a contagem errada").
export function YieldCard({
  daily,
  periodYieldKwhPerKwhM2,
  yieldAtypicalThresholdPercent,
  periodYieldSampleDays,
}: {
  daily: AnomalyDailyPoint[]
  periodYieldKwhPerKwhM2: MetricValue
  yieldAtypicalThresholdPercent: MetricValue
  periodYieldSampleDays: number
}) {
  const periodYield = toNumber(periodYieldKwhPerKwhM2)

  // Sem irradiância disponível (usina sem coordenadas configuradas) ou sem
  // nenhum dia com produção e irradiância positivas ao mesmo tempo, o
  // backend devolve `null` — o card simplesmente não existe, rendimento não
  // faz sentido sem o denominador (mesmo comportamento de antes da T7).
  if (periodYield == null) return null

  // Limiar malformado/ausente (nunca deveria acontecer — é uma política
  // fixa do backend, ver `AnomalyDashboardResponse.
  // yield_atypical_threshold_percent`) cai para "nenhum dia é atípico" em
  // vez de fabricar um limiar ou marcar tudo como atípico.
  const threshold = toNumber(yieldAtypicalThresholdPercent) ?? Infinity

  const atypicalDays = daily
    .map((d) => ({ date: d.date, deviationPercent: toNumber(d.yield_deviation_from_period_percent) }))
    .filter(
      (d): d is { date: string; deviationPercent: number } =>
        d.deviationPercent != null && Math.abs(d.deviationPercent) >= threshold
    )
    .sort((a, b) => Math.abs(b.deviationPercent) - Math.abs(a.deviationPercent))
    .slice(0, 3)

  return (
    <Card>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        Rendimento médio da janela analisada ({periodYieldSampleDays}{' '}
        {periodYieldSampleDays === 1 ? 'dia' : 'dias'})
      </p>
      <p className="mt-1 text-xs text-gray-500">kWh gerados por kWh/m² de sol recebido</p>
      <p className="mt-2 text-2xl font-semibold text-[var(--color-data-secondary)] tabular-nums">
        {formatNumber(periodYield, 2)}
        <span className="ml-1 text-sm font-normal text-gray-500">kWh/kWh·m²</span>
      </p>

      {atypicalDays.length === 0 ? (
        <p className="mt-4 text-xs text-gray-500">
          Rendimento estável — nenhum dia com desvio relevante em relação à janela analisada.
        </p>
      ) : (
        <>
          <p className="mt-4 text-xs font-medium uppercase tracking-wide text-gray-500">
            Dias com rendimento fora do padrão
          </p>
          <ul className="mt-2 space-y-2 text-xs text-gray-600">
            {atypicalDays.map((d) => (
              <li key={d.date} className="flex items-center justify-between gap-2">
                <span className="font-medium text-gray-900">{formatShortDate(d.date)}</span>
                <span>
                  {d.deviationPercent > 0 ? 'acima' : 'abaixo'} da média em{' '}
                  <strong className="text-gray-900 tabular-nums">
                    {formatNumber(Math.abs(d.deviationPercent), 0)}%
                  </strong>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-gray-500">
            Rendimento bem abaixo da média com sol disponível costuma indicar problema real na
            usina; bem acima costuma indicar dia de céu limpo apesar de pouca produção esperada.
          </p>
        </>
      )}
    </Card>
  )
}
