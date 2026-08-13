import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { YieldCard } from './YieldCard'
import type { AnomalyDailyPoint } from '../lib/dashboard/contracts'

// Todos os valores de rendimento/desvio abaixo já vêm prontos, como o
// backend (`intelligence/anomaly_service.py::_compute_period_yield`) os
// devolveria — este arquivo nunca soma/divide, só monta o payload de teste
// (mesmo espírito de `no-client-computed-yield-deviation.test.ts`, que
// garante que `YieldCard.tsx` também não faz isso).
function buildDaily(overrides: Partial<AnomalyDailyPoint> = {}): AnomalyDailyPoint {
  return {
    date: '2026-08-01',
    actual_production_kwh: 40,
    expected_production_kwh: 44,
    level: 'NORMAL',
    deviation_percent: -9,
    irradiation_kwh_m2: 5,
    yield_kwh_per_kwh_m2: 8,
    yield_deviation_from_period_percent: 0,
    diagnostics: [],
    ...overrides,
  }
}

describe('YieldCard', () => {
  it('não renderiza nada quando o backend não conseguiu calcular rendimento do período (sem irradiância)', () => {
    const { container } = render(
      <YieldCard
        daily={[buildDaily({ yield_kwh_per_kwh_m2: null, yield_deviation_from_period_percent: null })]}
        periodYieldKwhPerKwhM2={null}
        yieldAtypicalThresholdPercent="20"
        periodYieldSampleDays={7}
      />
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('mostra o rendimento da janela analisada, rotulado com `periodYieldSampleDays` (não `daysAnalyzed`)', () => {
    render(
      <YieldCard
        daily={[buildDaily()]}
        periodYieldKwhPerKwhM2="8.123"
        yieldAtypicalThresholdPercent="20"
        periodYieldSampleDays={90}
      />
    )

    expect(screen.getByText('Rendimento médio da janela analisada (90 dias)')).toBeInTheDocument()
    expect(screen.getByText('8,12')).toBeInTheDocument()
  })

  it('mostra mensagem de estabilidade quando nenhum dia atinge o limiar de desvio', () => {
    render(
      <YieldCard
        daily={[
          buildDaily({ date: '2026-08-01', yield_deviation_from_period_percent: 5 }),
          buildDaily({ date: '2026-08-02', yield_deviation_from_period_percent: -10 }),
        ]}
        periodYieldKwhPerKwhM2="8"
        yieldAtypicalThresholdPercent="20"
        periodYieldSampleDays={7}
      />
    )

    expect(
      screen.getByText('Rendimento estável — nenhum dia com desvio relevante em relação à janela analisada.')
    ).toBeInTheDocument()
    expect(screen.queryByText('Dias com rendimento fora do padrão')).not.toBeInTheDocument()
  })

  it('lista só os dias que cruzam o limiar vindo do backend, maior desvio primeiro, no máximo 3', () => {
    render(
      <YieldCard
        daily={[
          buildDaily({ date: '2026-08-01', yield_deviation_from_period_percent: 22 }),
          buildDaily({ date: '2026-08-02', yield_deviation_from_period_percent: -33 }),
          buildDaily({ date: '2026-08-03', yield_deviation_from_period_percent: 5 }), // abaixo do limiar
          buildDaily({ date: '2026-08-04', yield_deviation_from_period_percent: 27 }),
          buildDaily({ date: '2026-08-05', yield_deviation_from_period_percent: -21 }),
        ]}
        periodYieldKwhPerKwhM2="8"
        yieldAtypicalThresholdPercent="20"
        periodYieldSampleDays={7}
      />
    )

    expect(screen.getByText('Dias com rendimento fora do padrão')).toBeInTheDocument()
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(3)
    // Maior desvio absoluto primeiro (-33%), depois +27%, depois +22% — o
    // dia com +5% (abaixo do limiar de 20%) nunca aparece.
    expect(items[0]).toHaveTextContent('02/08')
    expect(items[0]).toHaveTextContent('abaixo da média em 33%')
    expect(items[1]).toHaveTextContent('04/08')
    expect(items[1]).toHaveTextContent('acima da média em 27%')
    expect(items[2]).toHaveTextContent('01/08')
    expect(items[2]).toHaveTextContent('acima da média em 22%')
    expect(screen.queryByText('03/08')).not.toBeInTheDocument()
    expect(screen.queryByText('05/08')).not.toBeInTheDocument()
  })

  it('nunca marca como atípico um dia sem desvio calculável (não reportou/sem irradiância naquele dia)', () => {
    render(
      <YieldCard
        daily={[
          buildDaily({
            date: '2026-08-01',
            yield_kwh_per_kwh_m2: null,
            yield_deviation_from_period_percent: null,
            diagnostics: [],
          }),
        ]}
        periodYieldKwhPerKwhM2="8"
        yieldAtypicalThresholdPercent="20"
        periodYieldSampleDays={7}
      />
    )

    expect(
      screen.getByText('Rendimento estável — nenhum dia com desvio relevante em relação à janela analisada.')
    ).toBeInTheDocument()
  })

  it('mostra um dia de produção zero sob sol pleno como o desvio mais grave (plano T7b, P1: "dia de produção zero com sol desaparece")', () => {
    // `yield_kwh_per_kwh_m2: 0`/`yield_deviation_from_period_percent: -100`
    // é exatamente o que o backend devolve pra um apagão (0 kWh) com
    // irradiância positiva — uma razão definida, não ausente (ver
    // `anomaly_service.py::_compute_period_yield`). Antes desta correção, um
    // dia assim tinha `yield_deviation_from_period_percent: null` e sumia da
    // lista de atípicos, como se não houvesse dado algum.
    render(
      <YieldCard
        daily={[
          buildDaily({ date: '2026-08-01', yield_kwh_per_kwh_m2: 0, yield_deviation_from_period_percent: -100 }),
          buildDaily({ date: '2026-08-02', yield_deviation_from_period_percent: 5 }),
        ]}
        periodYieldKwhPerKwhM2="8"
        yieldAtypicalThresholdPercent="20"
        periodYieldSampleDays={7}
      />
    )

    expect(screen.getByText('Dias com rendimento fora do padrão')).toBeInTheDocument()
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(1)
    expect(items[0]).toHaveTextContent('01/08')
    expect(items[0]).toHaveTextContent('abaixo da média em 100%')
  })
})
