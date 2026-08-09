import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MetricStrip } from './MetricStrip'

describe('MetricStrip', () => {
  it('renderiza cada item com rótulo, valor formatado e unidade, dentro de um único Card', () => {
    const { container } = render(
      <MetricStrip
        items={[
          { label: 'Tarifa com impostos', value: 0.85, unit: 'R$/kWh', maximumFractionDigits: 6 },
          { label: 'Saldo de créditos', value: 63.98, unit: 'kWh' },
        ]}
      />
    )

    // Um único Card (`rounded-2xl`) contendo os dois itens — não um Card por
    // item (esse é o ponto da tira: menos caixas, não menos dado).
    expect(container.querySelectorAll('.rounded-2xl')).toHaveLength(1)

    expect(screen.getByText('Tarifa com impostos')).toBeInTheDocument()
    expect(screen.getByText(/0,85/)).toBeInTheDocument()
    expect(screen.getByText('R$/kWh')).toBeInTheDocument()

    expect(screen.getByText('Saldo de créditos')).toBeInTheDocument()
    expect(screen.getByText(/63,98/)).toBeInTheDocument()
    expect(screen.getByText('kWh')).toBeInTheDocument()
  })

  it('mostra o traço quando o valor de um item é nulo, mas mantém a unidade visível', () => {
    render(<MetricStrip items={[{ label: 'Cobertura de créditos', value: null, unit: '%' }]} />)

    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText('%')).toBeInTheDocument()
  })

  it('expõe a barra de progresso com semântica ARIA só no item que informa barPercent', () => {
    render(
      <MetricStrip
        items={[
          { label: 'Tarifa com impostos', value: 0.85, unit: 'R$/kWh' },
          { label: 'Cobertura de créditos', value: 100, unit: '%', barPercent: 100 },
        ]}
      />
    )

    const progressbars = screen.getAllByRole('progressbar')
    expect(progressbars).toHaveLength(1)
    expect(progressbars[0]).toHaveAttribute('aria-valuenow', '100')
    expect(progressbars[0]).toHaveAttribute('aria-valuemin', '0')
    expect(progressbars[0]).toHaveAttribute('aria-valuemax', '100')
    expect(progressbars[0]).toHaveAttribute('aria-label', 'Cobertura de créditos')
  })

  it('o valor numérico principal de cada item usa tabular-nums (mesmo padrão de MetricCard)', () => {
    render(<MetricStrip items={[{ label: 'Saldo de créditos', value: 63.98, unit: 'kWh' }]} />)

    const valueNode = screen.getByText(/63,98/)
    expect(valueNode.className).toMatch(/\btabular-nums\b/)
  })

  it('cada item vive na sua própria coluna (elemento próprio), não um bloco de texto único', () => {
    render(
      <MetricStrip
        items={[
          { label: 'Tarifa com impostos', value: 0.85, unit: 'R$/kWh' },
          { label: 'Tarifa sem impostos', value: 0.6, unit: 'R$/kWh' },
        ]}
      />
    )

    const firstLabel = screen.getByText('Tarifa com impostos')
    const secondLabel = screen.getByText('Tarifa sem impostos')
    expect(firstLabel.closest('div')).not.toBe(secondLabel.closest('div'))
    expect(within(firstLabel.closest('div') as HTMLElement).getByText(/0,85/)).toBeInTheDocument()
  })
})
