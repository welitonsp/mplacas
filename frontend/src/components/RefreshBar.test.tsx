import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { RefreshBar } from './RefreshBar'

describe('RefreshBar', () => {
  it('mostra "Atualizar" quando loading é false, e chama onRefresh ao clicar', () => {
    const onRefresh = vi.fn()
    render(<RefreshBar onRefresh={onRefresh} loading={false} />)

    const button = screen.getByRole('button', { name: 'Atualizar' })
    expect(button).not.toBeDisabled()

    fireEvent.click(button)
    expect(onRefresh).toHaveBeenCalledTimes(1)
  })

  it('mostra "Atualizando..." e desabilita o botão quando loading é true', () => {
    const onRefresh = vi.fn()
    render(<RefreshBar onRefresh={onRefresh} loading={true} />)

    const button = screen.getByRole('button', { name: 'Atualizando...' })
    expect(button).toBeDisabled()

    // Botão desabilitado não dispara onClick.
    fireEvent.click(button)
    expect(onRefresh).not.toHaveBeenCalled()
  })

  it('a className do botão inclui focus-visible:ring (mesma classe preservada dos módulos)', () => {
    render(<RefreshBar onRefresh={vi.fn()} loading={false} />)

    const button = screen.getByRole('button', { name: 'Atualizar' })
    expect(button.className).toMatch(/focus-visible:ring/)
  })
})
