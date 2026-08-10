import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { OperationalState } from './OperationalState'

describe('OperationalState', () => {
  it('renderiza estado informativo com contexto executivo e ação', () => {
    render(
      <OperationalState
        eyebrow="Dados incompletos"
        title="Leitura parcial do ciclo"
        description="Alguns indicadores ainda não chegaram. Use a decisão com cautela."
        action={<button type="button">Atualizar leitura</button>}
        tone="warning"
        icon="sync"
        role="status"
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent('Dados incompletos')
    expect(screen.getByRole('heading', { level: 2, name: 'Leitura parcial do ciclo' })).toBeInTheDocument()
    expect(screen.getByText('Alguns indicadores ainda não chegaram. Use a decisão com cautela.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Atualizar leitura' })).toBeInTheDocument()
  })

  it('renderiza alerta alinhado à esquerda para falhas operacionais', () => {
    render(
      <OperationalState
        title="Não foi possível carregar os dados"
        description="Tente novamente em alguns instantes."
        tone="danger"
        icon="warning"
        role="alert"
        align="start"
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível carregar os dados')
    expect(screen.getByText('Tente novamente em alguns instantes.')).toBeInTheDocument()
  })

  it('aceita landmark complementar com rótulo acessível', () => {
    render(
      <OperationalState
        role="complementary"
        ariaLabel="Confiança dos dados"
        title="Dados prontos para decisão"
        description="Última leitura diária consolidada."
        tone="success"
        icon="check"
      />,
    )

    const landmark = screen.getByRole('complementary', { name: 'Confiança dos dados' })
    expect(landmark).toHaveTextContent('Dados prontos para decisão')
  })
})
