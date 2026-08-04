import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AttentionSummary } from './AttentionSummary'
import type { Diagnostic } from '../lib/dashboard/contracts'

function buildDiagnostic(overrides: Partial<Diagnostic> = {}): Diagnostic {
  return {
    code: 'SOME_CODE',
    severity: 'WARNING',
    message: 'Algo precisa de atenção',
    recommended_action: 'Verifique o painel',
    ...overrides,
  }
}

describe('AttentionSummary', () => {
  it('não renderiza nada quando não há diagnóstico CRITICAL', () => {
    const { container } = render(
      <AttentionSummary diagnostics={[buildDiagnostic({ severity: 'WARNING' }), buildDiagnostic({ severity: 'INFO' })]} />
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('não renderiza nada com lista de diagnósticos vazia', () => {
    const { container } = render(<AttentionSummary diagnostics={[]} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('mostra a contagem de críticos e atenção, com âncora para a seção de diagnósticos', () => {
    render(
      <AttentionSummary
        diagnostics={[
          buildDiagnostic({ code: 'A', severity: 'CRITICAL' }),
          buildDiagnostic({ code: 'B', severity: 'CRITICAL' }),
          buildDiagnostic({ code: 'C', severity: 'WARNING' }),
        ]}
      />
    )

    const link = screen.getByRole('link', { name: /2 críticos, 1 atenção/ })
    expect(link).toHaveAttribute('href', '#diagnosticos')
  })

  it('omite a contagem de atenção quando não há diagnóstico WARNING', () => {
    render(<AttentionSummary diagnostics={[buildDiagnostic({ code: 'A', severity: 'CRITICAL' })]} />)

    expect(screen.getByRole('link', { name: /1 crítico — ver diagnósticos/ })).toBeInTheDocument()
  })
})
