import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErrorBoundary } from './ErrorBoundary'

function Bomb(): never {
  throw new Error('boom')
}

describe('ErrorBoundary', () => {
  it('renderiza os filhos normalmente quando não há erro', () => {
    render(
      <ErrorBoundary>
        <p>Conteúdo normal</p>
      </ErrorBoundary>
    )

    expect(screen.getByText('Conteúdo normal')).toBeInTheDocument()
  })

  it('mostra uma mensagem amigável (sem detalhes técnicos) quando um filho lança durante o render', () => {
    // React loga o erro capturado no console mesmo com um ErrorBoundary —
    // silenciamos aqui só para não poluir a saída do teste.
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>
    )

    expect(screen.getByText('Não foi possível carregar o Mplacas')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Recarregar' })).toBeInTheDocument()

    // Nunca vazar a mensagem de erro técnica ("boom") na tela.
    expect(screen.queryByText(/boom/)).not.toBeInTheDocument()

    consoleErrorSpy.mockRestore()
  })
})
