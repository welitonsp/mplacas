import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PatrimonyLines, crossoverYear } from './PatrimonyLines'

const points = [
  { year: 0, cdi: 10000, solar: 0 },
  { year: 5, cdi: 17000, solar: 15000 },
  { year: 10, cdi: 29000, solar: 45000 },
]

describe('PatrimonyLines', () => {
  it('calcula o ano em que a usina passa o CDI por interpolação', () => {
    // entre ano 5 (−2.000) e ano 10 (+16.000): 5 + 2/18 × 5 ≈ 5,56
    expect(crossoverYear(points)).toBeCloseTo(5.556, 2)
    expect(crossoverYear([{ year: 0, cdi: 10, solar: 0 }, { year: 1, cdi: 20, solar: 5 }])).toBeNull()
  })

  it('desenha um gráfico nomeado com a marca do cruzamento e tabela para leitor de tela', () => {
    render(<PatrimonyLines points={points} ariaLabel="Patrimônio em 10 anos" />)
    expect(screen.getByRole('img', { name: 'Patrimônio em 10 anos' })).toBeInTheDocument()
    expect(screen.getByText(/usina passa o CDI ≈ ano 5,6/)).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(4)
  })

  it('usa o cruzamento calculado pelo backend quando informado, e omite a marca se nunca cruza', () => {
    const { rerender } = render(<PatrimonyLines points={points} crossover={55 / 12} ariaLabel="P" />)
    expect(screen.getByText(/usina passa o CDI ≈ ano 4,6/)).toBeInTheDocument()
    rerender(<PatrimonyLines points={points} crossover={null} ariaLabel="P" />)
    expect(screen.queryByText(/passa o CDI/)).toBeNull()
  })
})
