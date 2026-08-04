import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CurrencyCard } from './CurrencyCard'

describe('CurrencyCard', () => {
  it('renderiza label e valor formatado em R$', () => {
    render(<CurrencyCard label="Componente de energia" value={123.45} />)

    expect(screen.getByText('Componente de energia')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s*123,45/)).toBeInTheDocument()
  })

  it('mantém a unidade R$ visível mesmo quando o valor é nulo', () => {
    render(<CurrencyCard label="Componente de energia" value={null} />)

    expect(screen.getByText(/R\$\s*—/)).toBeInTheDocument()
  })

  it('o valor numérico principal usa tabular-nums (Etapa 1.5)', () => {
    render(<CurrencyCard label="Componente de energia" value={123.45} />)

    const valueNode = screen.getByText(/R\$\s*123,45/)
    expect(valueNode.className).toMatch(/\btabular-nums\b/)
  })
})
