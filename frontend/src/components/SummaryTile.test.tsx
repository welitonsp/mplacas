import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SummaryTile } from './SummaryTile'

describe('SummaryTile', () => {
  it('renderiza o resumo executivo com label, valor e texto de apoio', () => {
    render(
      <SummaryTile
        label="Saúde técnica"
        value="Atenção"
        supportingText="PR bruto 82%"
        tone="warning"
      />
    )

    expect(screen.getByText('Saúde técnica')).toBeInTheDocument()
    expect(screen.getByText('Atenção')).toBeInTheDocument()
    expect(screen.getByText('PR bruto 82%')).toBeInTheDocument()
  })

  it('usa tokens de marca para tone=brand', () => {
    render(
      <SummaryTile
        label="Última produção"
        value="40 kWh"
        supportingText="Dado de 30/07/2026"
        tone="brand"
      />
    )

    expect(screen.getByText('40 kWh').closest('article')?.className).toContain(
      'border-[var(--color-border)]'
    )
    expect(screen.getByText('Dado de 30/07/2026').className).toContain(
      'bg-[var(--color-brand-primary-light)]'
    )
  })

  it('mantém valor principal com tabular-nums para leitura financeira/operacional', () => {
    render(
      <SummaryTile
        label="Desvio"
        value="-9%"
        supportingText="Atenção"
        tone="danger"
      />
    )

    expect(screen.getByText('-9%').className).toContain('tabular-nums')
  })
})
