import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { HeroCard } from './HeroCard'
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

describe('HeroCard', () => {
  it('expõe o gauge de saúde da usina com semântica ARIA e valor correto', () => {
    render(
      <HeroCard
        referenceMonth="2026-07"
        headline="Usina operando normalmente"
        status="NORMAL"
        healthScore={85}
      />
    )

    const gauge = screen.getByRole('img')
    expect(gauge).toHaveAttribute('aria-label', 'Saúde da usina: 85/100')
  })

  it('não renderiza o gauge quando o health score é nulo', () => {
    render(
      <HeroCard referenceMonth="2026-07" headline="Sem dado" status="NORMAL" healthScore={null} />
    )

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('o valor da saúde da usina usa tabular-nums (Etapa 1.5)', () => {
    render(
      <HeroCard referenceMonth="2026-07" headline="Usina operando normalmente" status="NORMAL" healthScore={85} />
    )

    const valueNode = screen.getByText('85/100')
    expect(valueNode.className).toMatch(/\btabular-nums\b/)
  })

  it('mostra o chip de atenção com a contagem quando há diagnóstico CRITICAL (Etapa 1.7)', () => {
    render(
      <HeroCard
        referenceMonth="2026-07"
        headline="Ciclo requer atenção"
        status="CRITICAL"
        healthScore={40}
        diagnostics={[
          buildDiagnostic({ code: 'A', severity: 'CRITICAL' }),
          buildDiagnostic({ code: 'B', severity: 'WARNING' }),
          buildDiagnostic({ code: 'C', severity: 'WARNING' }),
        ]}
      />
    )

    const chip = screen.getByText(/1 crítico, 2 atenção/)
    expect(chip.closest('a')).toHaveAttribute('href', '#diagnosticos')
  })

  it('não mostra o chip de atenção quando não há diagnóstico CRITICAL', () => {
    render(
      <HeroCard
        referenceMonth="2026-07"
        headline="Ciclo normal"
        status="NORMAL"
        healthScore={95}
        diagnostics={[buildDiagnostic({ code: 'B', severity: 'WARNING' })]}
      />
    )

    expect(screen.queryByText(/crítico/)).not.toBeInTheDocument()
  })

  it('não mostra o chip de atenção quando não há diagnósticos', () => {
    render(<HeroCard referenceMonth="2026-07" headline="Ciclo normal" status="NORMAL" healthScore={95} />)

    expect(screen.queryByText(/crítico/)).not.toBeInTheDocument()
  })
})
