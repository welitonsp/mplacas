import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { ProductionHistoryChart } from './ProductionHistoryChart'
import type { AnomalyDailyPoint } from '../lib/dashboard/contracts'

function buildDaily(date: string, actual: number, overrides: Partial<AnomalyDailyPoint> = {}): AnomalyDailyPoint {
  return {
    date,
    actual_production_kwh: actual,
    expected_production_kwh: 50,
    level: 'NORMAL',
    deviation_percent: -9,
    irradiation_kwh_m2: null,
    ...overrides,
  }
}

const DAILY: AnomalyDailyPoint[] = [
  buildDaily('2026-07-01', 10),
  buildDaily('2026-07-02', 20),
  buildDaily('2026-07-03', 30),
]

describe('ProductionHistoryChart — teclado e semântica ARIA', () => {
  it('é um único tab stop (role=slider) e não cria um <button> por dia', () => {
    render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    expect(screen.getAllByRole('slider')).toHaveLength(1)
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('mostra o último dia selecionado por padrão', () => {
    render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    expect(screen.getByRole('slider')).toHaveAttribute('aria-valuenow', '2')
  })

  it('seta esquerda/direita move o dia selecionado', () => {
    render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    const slider = screen.getByRole('slider')
    slider.focus()

    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    expect(slider).toHaveAttribute('aria-valuenow', '1')

    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    expect(slider).toHaveAttribute('aria-valuenow', '0')

    // Não passa do limite inferior.
    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    expect(slider).toHaveAttribute('aria-valuenow', '0')

    fireEvent.keyDown(slider, { key: 'ArrowRight' })
    expect(slider).toHaveAttribute('aria-valuenow', '1')
  })

  it('o painel de detalhe do dia selecionado tem aria-live="polite"', () => {
    const { container } = render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    const liveRegion = container.querySelector('[aria-live="polite"]')
    expect(liveRegion).toBeInTheDocument()
    expect(liveRegion).toHaveTextContent('30 kWh')
  })

  it('a régua de datas é descendente do mesmo container overflow-x-auto que as barras (Etapa 1.3)', () => {
    const { container } = render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    const scrollContainer = container.querySelector('.overflow-x-auto')
    expect(scrollContainer).not.toBeNull()

    const slider = screen.getByRole('slider')
    expect(scrollContainer!.contains(slider)).toBe(true)

    // Rótulo do primeiro dia — a régua de datas precisa estar dentro do mesmo
    // container que rola horizontalmente junto com as barras, não fora dele.
    const firstDateLabels = screen.getAllByText('01/07')
    expect(firstDateLabels.some((label) => scrollContainer!.contains(label))).toBe(true)
  })

  it('mostra a data curta no topo de cada barra quando o recorte tem até 7 dias', () => {
    const daily = Array.from({ length: 7 }, (_, index) =>
      buildDaily(`2026-08-${String(index + 2).padStart(2, '0')}`, (index + 1) * 10)
    )

    render(<ProductionHistoryChart daily={daily} currentStreakDays={0} />)

    const dateLabels = screen.getAllByTestId('production-bar-date-label')
    expect(dateLabels).toHaveLength(7)
    expect(dateLabels.map((label) => label.textContent)).toEqual([
      '02/08',
      '03/08',
      '04/08',
      '05/08',
      '06/08',
      '07/08',
      '08/08',
    ])
  })

  it('não mostra data no topo das barras em recortes maiores para evitar poluição visual', () => {
    const daily = Array.from({ length: 30 }, (_, index) =>
      buildDaily(`2026-08-${String((index % 28) + 1).padStart(2, '0')}`, (index + 1) * 2)
    )

    render(<ProductionHistoryChart daily={daily} currentStreakDays={0} />)

    expect(screen.queryAllByTestId('production-bar-date-label')).toHaveLength(0)
  })

  it('mostra leitura executiva com total produzido, melhor dia e pior dia do período', () => {
    render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    const readout = screen.getByTestId('production-period-readout')
    expect(readout).toHaveTextContent('Total produzido')
    expect(readout).toHaveTextContent('60 kWh')
    expect(readout).toHaveTextContent('Melhor dia')
    expect(readout).toHaveTextContent('30 kWh')
    expect(readout).toHaveTextContent('em 03/07')
    expect(readout).toHaveTextContent('Pior dia')
    expect(readout).toHaveTextContent('10 kWh')
    expect(readout).toHaveTextContent('em 01/07')
  })

  it('mantém o dia selecionado explicitamente ao invés de resetar para o último dia', () => {
    render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    const slider = screen.getByRole('slider')
    slider.focus()
    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    expect(slider).toHaveAttribute('aria-valuenow', '0')

    // "Sair" do gráfico (blur) não deve resetar a seleção para o último dia.
    slider.blur()
    expect(slider).toHaveAttribute('aria-valuenow', '0')
  })
})

describe('ProductionHistoryChart — dia sem expectativa (level: null)', () => {
  it('renderiza sem lançar erro e usa tom neutro para o dia com level: null', () => {
    const dailyWithNullLevel: AnomalyDailyPoint[] = [
      buildDaily('2026-07-01', 10, { expected_production_kwh: null, level: null, deviation_percent: null }),
      buildDaily('2026-07-02', 20),
      buildDaily('2026-07-03', 30),
    ]

    render(<ProductionHistoryChart daily={dailyWithNullLevel} currentStreakDays={0} />)

    // A legenda ganha uma entrada explícita pra explicar o tom neutro — cor
    // nunca aparece sem rótulo (regra de acessibilidade).
    expect(screen.getByText('Sem expectativa')).toBeInTheDocument()
  })

  it('o aria-label do dia ativo não menciona "esperado" nem fabrica um nível quando expected_production_kwh é null', () => {
    const dailyWithNullLevel: AnomalyDailyPoint[] = [
      buildDaily('2026-07-01', 10),
      buildDaily('2026-07-02', 20),
      buildDaily('2026-07-03', 40, { expected_production_kwh: null, level: null, deviation_percent: null }),
    ]

    render(<ProductionHistoryChart daily={dailyWithNullLevel} currentStreakDays={0} />)

    const slider = screen.getByRole('slider')
    expect(slider).toHaveAttribute('aria-valuetext', '03/07: 40 kWh produzidos.')
    expect(slider.getAttribute('aria-valuetext')).not.toMatch(/esperado/i)
  })

  it('o painel de detalhe do dia ativo não mostra "Esperado" quando o valor é null, mas mostra o nível em tom neutro ("Sem expectativa")', () => {
    const dailyWithNullLevel: AnomalyDailyPoint[] = [
      buildDaily('2026-07-01', 10),
      buildDaily('2026-07-02', 20),
      buildDaily('2026-07-03', 40, { expected_production_kwh: null, level: null, deviation_percent: null }),
    ]

    render(<ProductionHistoryChart daily={dailyWithNullLevel} currentStreakDays={0} />)

    const liveRegion = document.querySelector('[aria-live="polite"]')
    expect(liveRegion).toBeInTheDocument()
    expect(within(liveRegion as HTMLElement).getByText('40 kWh')).toBeInTheDocument()
    expect(screen.queryByText(/Esperado:/)).not.toBeInTheDocument()
    // Aparece duas vezes: uma na legenda (explicando a cor) e outra como
    // rótulo de nível do dia ativo no painel de detalhe.
    expect(screen.getAllByText('Sem expectativa').length).toBeGreaterThanOrEqual(2)
  })

  it('não soma zero fabricado nos dias sem expectativa ao calcular o percentual de desempenho do período', () => {
    // Só o dia 2 tem par completo (actual=20, expected=50) — desempenho =
    // 20/50 = 40%. Se os dias sem expectativa contribuíssem com `expected=0`,
    // o total esperado cairia pra 50 (igual), mas se contribuíssem só no
    // `actual` sem entrar no `expected`, o percentual ficaria inflado
    // (60/50 = 120%) em vez dos 40% corretos.
    const mixedDaily: AnomalyDailyPoint[] = [
      buildDaily('2026-07-01', 10, { expected_production_kwh: null, level: null, deviation_percent: null }),
      buildDaily('2026-07-02', 20, { expected_production_kwh: 50 }),
      buildDaily('2026-07-03', 30, { expected_production_kwh: null, level: null, deviation_percent: null }),
    ]

    render(<ProductionHistoryChart daily={mixedDaily} currentStreakDays={0} />)

    expect(screen.getByText(/Desempenho: 40%/)).toBeInTheDocument()
  })
})

describe('ProductionHistoryChart — eixo Y e linha de referência esperada (baseline sazonal)', () => {
  it('mostra o eixo Y com rótulos numéricos de 0, metade e máximo, baseados no maxValue real', () => {
    // maxValue = max(actual, expected) do conjunto (expected=50 em todo dia) * 1.1 = 55.
    render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    expect(screen.getByText('55 kWh')).toBeInTheDocument()
    expect(screen.getByText('28 kWh')).toBeInTheDocument()
    expect(screen.getByText('0 kWh')).toBeInTheDocument()
  })

  it('desenha a linha de referência esperada como uma única linha horizontal, não um traço por barra (o valor é o mesmo escalar em todos os dias)', () => {
    const { container } = render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    // Um único elemento `<line>` de referência, não um `<path>`/traço por dia.
    const referenceLines = container.querySelectorAll('line[stroke="var(--color-chart-reference)"]')
    expect(referenceLines).toHaveLength(1)
    // A linha cobre a largura inteira do gráfico (0 até o total de dias), não
    // um segmento por barra — mesmo padrão da linha "Média do período".
    expect(referenceLines[0]).toHaveAttribute('x1', '0')
    expect(referenceLines[0]).toHaveAttribute('x2', String(DAILY.length))
    expect(referenceLines[0].getAttribute('y1')).toBe(referenceLines[0].getAttribute('y2'))
    expect(container.querySelectorAll('path[stroke-dasharray]')).toHaveLength(0)

    // Rótulo não afirma expectativa por dia — deixa explícito que é a média
    // diária do período (baseline sazonal), não uma previsão diária.
    expect(screen.getByText('Média diária esperada (baseline sazonal)')).toBeInTheDocument()
    expect(screen.queryByText('Esperado')).not.toBeInTheDocument()
  })

  it('desenha uma linha de média do período e mostra o valor no painel de detalhe', () => {
    const { container } = render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    expect(screen.getByText('Média do período')).toBeInTheDocument()
    expect(screen.getByText('20 kWh/dia')).toBeInTheDocument()
    expect(screen.getByText('1 dia abaixo da média')).toBeInTheDocument()
    expect(screen.getByText('Vs. média: +50%')).toBeInTheDocument()
    expect(container.querySelector('line[stroke="var(--color-brand-primary)"]')).toBeInTheDocument()
  })

  it('não desenha a linha de referência esperada quando expectedAvailable é false, mas as barras de produção real continuam', () => {
    const { container } = render(
      <ProductionHistoryChart daily={DAILY} currentStreakDays={0} expectedAvailable={false} />
    )

    expect(container.querySelectorAll('path[stroke-dasharray]')).toHaveLength(0)
    expect(container.querySelectorAll('line[stroke="var(--color-chart-reference)"]')).toHaveLength(0)
    expect(screen.queryByText('Média diária esperada (baseline sazonal)')).not.toBeInTheDocument()
    expect(screen.queryByText('Esperado')).not.toBeInTheDocument()
    // As barras de produção real continuam presentes.
    expect(screen.getByRole('slider')).toBeInTheDocument()
  })

  it('o painel de detalhe do dia rotula o valor como "Baseline esperado (período)" em kWh/dia, não como expectativa daquele dia', () => {
    render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    const liveRegion = document.querySelector('[aria-live="polite"]') as HTMLElement
    expect(within(liveRegion).getByText('Baseline esperado (período):')).toBeInTheDocument()
    expect(within(liveRegion).getByText('50 kWh/dia')).toBeInTheDocument()
    // Rótulo antigo, que sugeria uma expectativa específica do dia, não pode
    // mais aparecer.
    expect(within(liveRegion).queryByText('Esperado:')).not.toBeInTheDocument()
  })

  it('o texto acessível (aria-valuetext) do dia ativo descreve o valor esperado como baseline do período, não como expectativa do dia', () => {
    render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    const slider = screen.getByRole('slider')
    expect(slider).toHaveAttribute(
      'aria-valuetext',
      '03/07: 30 kWh produzidos. Baseline esperado do período: 50 kWh/dia. Nível: Normal.'
    )
  })
})

describe('ProductionHistoryChart — classificação por dia permanece inalterada pela correção de rótulo/desenho (T5)', () => {
  it('mostra, para cada dia navegado, exatamente o nível e a severidade que o backend calculou em `level` — a mudança de rótulo/linha do "esperado" não recalcula nem reclassifica nada no cliente', () => {
    // Três dias com níveis distintos vindos prontos do backend (mesmo valor
    // escalar de `expected_production_kwh` em todos, como no payload real —
    // ver `anomaly_service.py:145-171` — mas `level`/`deviation_percent` já
    // diferem por dia, calculados por `assess_daily_performance` no backend,
    // não recalculados aqui).
    const mixedLevels: AnomalyDailyPoint[] = [
      buildDaily('2026-07-01', 48, { level: 'NORMAL', deviation_percent: -4 }),
      buildDaily('2026-07-02', 35, { level: 'ATTENTION', deviation_percent: -30 }),
      buildDaily('2026-07-03', 15, { level: 'CRITICAL', deviation_percent: -70 }),
    ]

    render(<ProductionHistoryChart daily={mixedLevels} currentStreakDays={0} />)

    const slider = screen.getByRole('slider')
    const liveRegion = document.querySelector('[aria-live="polite"]') as HTMLElement

    // Dia 3 (índice 2) é o padrão inicial — nível CRÍTICO, como veio do backend.
    expect(within(liveRegion).getByText('Crítico')).toBeInTheDocument()

    slider.focus()
    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    expect(slider).toHaveAttribute('aria-valuenow', '1')
    expect(within(liveRegion).getByText('Atenção')).toBeInTheDocument()

    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    expect(slider).toHaveAttribute('aria-valuenow', '0')
    expect(within(liveRegion).getByText('Normal')).toBeInTheDocument()
  })
})
