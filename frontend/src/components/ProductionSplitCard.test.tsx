import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProductionSplitCard } from './ProductionSplitCard'

describe('ProductionSplitCard', () => {
  it('expõe a barra de composição com semântica ARIA de progressbar', () => {
    render(<ProductionSplitCard selfConsumption={60} injected={40} />)

    const progressbar = screen.getByRole('progressbar')
    expect(progressbar).toHaveAttribute('aria-valuenow', '60')
    expect(progressbar).toHaveAttribute('aria-valuemin', '0')
    expect(progressbar).toHaveAttribute('aria-valuemax', '100')
  })

  it('não renderiza a barra quando não há dados suficientes', () => {
    render(<ProductionSplitCard selfConsumption={null} injected={null} />)

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.getByText('Dados insuficientes para o gráfico.')).toBeInTheDocument()
  })
})
