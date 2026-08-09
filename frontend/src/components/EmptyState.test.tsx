import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('renderiza título, descrição, eyebrow e ação opcional', () => {
    render(
      <EmptyState
        eyebrow="Configuração"
        title="Nenhuma usina cadastrada"
        description="Cadastre uma usina para começar."
        action={<button type="button">Configurar</button>}
        tone="brand"
      />
    )

    expect(screen.getByText('Configuração')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Nenhuma usina cadastrada' })).toBeInTheDocument()
    expect(screen.getByText('Cadastre uma usina para começar.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Configurar' })).toBeInTheDocument()
  })
})
