import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { HeroCard } from './HeroCard'

describe('HeroCard', () => {
  it('expõe a barra de saúde da usina com semântica ARIA de progressbar', () => {
    render(
      <HeroCard
        referenceMonth="2026-07"
        headline="Usina operando normalmente"
        status="NORMAL"
        healthScore={85}
      />
    )

    const progressbar = screen.getByRole('progressbar')
    expect(progressbar).toHaveAttribute('aria-valuenow', '85')
    expect(progressbar).toHaveAttribute('aria-valuemin', '0')
    expect(progressbar).toHaveAttribute('aria-valuemax', '100')
  })

  it('não renderiza a barra quando o health score é nulo', () => {
    render(
      <HeroCard referenceMonth="2026-07" headline="Sem dado" status="NORMAL" healthScore={null} />
    )

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
})
