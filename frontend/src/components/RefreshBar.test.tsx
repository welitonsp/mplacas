import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { RefreshBar } from './RefreshBar'

describe('RefreshBar', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

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

  it('mostra feedback operacional antes, durante e depois da atualização manual', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-09T14:35:00-03:00'))

    const onRefresh = vi.fn()
    const { rerender } = render(<RefreshBar onRefresh={onRefresh} loading={false} />)

    expect(screen.getByText('Dados podem ser sincronizados manualmente')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Atualizar' }))
    expect(screen.getByText(/Atualização solicitada às 14:35/)).toBeInTheDocument()

    rerender(<RefreshBar onRefresh={onRefresh} loading={true} />)
    expect(screen.getByText('Sincronizando dados do painel')).toBeInTheDocument()
  })

  it('a className do botão inclui focus-visible:ring (mesma classe preservada dos módulos)', () => {
    render(<RefreshBar onRefresh={vi.fn()} loading={false} />)

    const button = screen.getByRole('button', { name: 'Atualizar' })
    expect(button.className).toMatch(/focus-visible:ring/)
  })
})
