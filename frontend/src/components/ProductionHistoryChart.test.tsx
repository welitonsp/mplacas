import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
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
    const firstDateLabel = screen.getByText('01/07')
    expect(scrollContainer!.contains(firstDateLabel)).toBe(true)
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

describe('ProductionHistoryChart — eixo Y e linha de "Esperado"', () => {
  it('mostra o eixo Y com rótulos numéricos de 0, metade e máximo, baseados no maxValue real', () => {
    // maxValue = max(actual, expected) do conjunto (expected=50 em todo dia) * 1.1 = 55.
    render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    expect(screen.getByText('55 kWh')).toBeInTheDocument()
    expect(screen.getByText('28 kWh')).toBeInTheDocument()
    expect(screen.getByText('0 kWh')).toBeInTheDocument()
  })

  it('desenha a linha de "Esperado" como uma única polilinha contínua quando a expectativa está disponível', () => {
    const { container } = render(<ProductionHistoryChart daily={DAILY} currentStreakDays={0} />)

    // Um único elemento de linha conectando os pontos, não N traços por barra.
    const paths = container.querySelectorAll('path[stroke-dasharray]')
    expect(paths).toHaveLength(1)
    // `M`/`L` para os 3 dias — uma polilinha contínua, sem reiniciar o traço.
    expect(paths[0].getAttribute('d')).toMatch(/^M0\.5 .+ L1\.5 .+ L2\.5 /)

    expect(screen.getByText('Esperado')).toBeInTheDocument()
  })

  it('não desenha a linha de "Esperado" quando expectedAvailable é false, mas as barras de produção real continuam', () => {
    const { container } = render(
      <ProductionHistoryChart daily={DAILY} currentStreakDays={0} expectedAvailable={false} />
    )

    expect(container.querySelectorAll('path[stroke-dasharray]')).toHaveLength(0)
    expect(screen.queryByText('Esperado')).not.toBeInTheDocument()
    // As barras de produção real continuam presentes.
    expect(screen.getByRole('slider')).toBeInTheDocument()
  })
})
