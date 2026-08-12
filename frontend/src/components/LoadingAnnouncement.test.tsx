import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { LoadingAnnouncement } from './LoadingAnnouncement'

describe('LoadingAnnouncement', () => {
  it('é uma live region "polite", separada de qualquer botão', () => {
    const { container } = render(<LoadingAnnouncement active={true} message="Salvando, aguarde." />)

    const liveRegion = container.querySelector('[aria-live="polite"]')
    expect(liveRegion).toBeInTheDocument()
    expect(liveRegion?.tagName).toBe('SPAN')
    expect(liveRegion).toHaveTextContent('Salvando, aguarde.')
  })

  it('fica vazia quando não está ativa, para não gerar anúncio sem mudança real de estado', () => {
    const { container } = render(<LoadingAnnouncement active={false} message="Salvando, aguarde." />)

    const liveRegion = container.querySelector('[aria-live="polite"]')
    expect(liveRegion).toBeInTheDocument()
    expect(liveRegion).toHaveTextContent('')
  })

  it('é visualmente oculta (sr-only), sem introduzir nenhuma UI nova', () => {
    const { container } = render(<LoadingAnnouncement active={true} message="Gerando, aguarde." />)

    const liveRegion = container.querySelector('[aria-live="polite"]')
    expect(liveRegion?.className).toMatch(/\bsr-only\b/)
  })
})
