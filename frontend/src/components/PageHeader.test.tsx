import { createRef } from 'react'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PageHeader } from './PageHeader'

describe('PageHeader', () => {
  it('renderiza eyebrow, h1 focável, descrição e ação', () => {
    const headingRef = createRef<HTMLHeadingElement>()

    render(
      <PageHeader
        eyebrow="Painel executivo"
        title="Visão Geral"
        description="Saúde, energia e resultado da sua usina em um só lugar."
        headingRef={headingRef}
        insights={[
          { label: 'Pergunta', value: 'A usina exige decisão agora?' },
          { label: 'Leitura', value: 'Saúde, energia e caixa' },
          { label: 'Saída', value: 'Prioridade executiva' },
        ]}
        actions={<button type="button">Atualizar</button>}
      />,
    )

    const heading = screen.getByRole('heading', { level: 1, name: 'Visão Geral' })
    expect(screen.getByText('Painel executivo')).toBeInTheDocument()
    expect(screen.getByText('Saúde, energia e resultado da sua usina em um só lugar.')).toBeInTheDocument()
    expect(screen.getByText('Pergunta')).toBeInTheDocument()
    expect(screen.getByText('A usina exige decisão agora?')).toBeInTheDocument()
    expect(screen.getByText('Saúde, energia e caixa')).toBeInTheDocument()
    expect(screen.getByText('Prioridade executiva')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Atualizar' })).toBeInTheDocument()
    expect(heading).toHaveAttribute('tabindex', '-1')
    expect(headingRef.current).toBe(heading)
  })

  it('mantém a faixa executiva opcional', () => {
    render(
      <PageHeader
        eyebrow="Painel técnico"
        title="Técnico"
        description="Diagnóstico da operação."
      />,
    )

    expect(screen.getByRole('heading', { level: 1, name: 'Técnico' })).toBeInTheDocument()
    expect(screen.queryByText('Pergunta')).not.toBeInTheDocument()
  })
})
