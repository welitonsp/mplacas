import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DashboardHeader } from './DashboardHeader'

describe('DashboardHeader', () => {
  it('o botão "Sair" tem estado de foco visível (focus-visible:ring)', () => {
    render(<DashboardHeader onLogout={vi.fn()} />)

    expect(screen.getByText('Sair').className).toMatch(/focus-visible:ring/)
  })
})
