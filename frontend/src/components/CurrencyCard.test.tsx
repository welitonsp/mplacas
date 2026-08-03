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
})
