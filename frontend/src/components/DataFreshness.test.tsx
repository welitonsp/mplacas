import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DataFreshness } from './DataFreshness'

describe('DataFreshness', () => {
  beforeEach(() => {
    // Trava o relógio bem longe da data do dado para provar que o texto exibido
    // vem do dado real coletado, não de `new Date()` no momento do fetch.
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-03T23:59:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('mostra a data do último dado real coletado, não a hora do fetch', () => {
    render(<DataFreshness latestDataDate="2026-07-30" lastSyncedAt={new Date()} />)

    expect(screen.getByText('Dado mais recente: 30/07/2026')).toBeInTheDocument()
    expect(screen.queryByText(/23:59/)).not.toBeInTheDocument()
  })

  it('cai para o horário de sincronização quando ainda não há data de dado real disponível', () => {
    const lastSyncedAt = new Date('2026-08-03T10:15:30Z')
    render(<DataFreshness latestDataDate={null} lastSyncedAt={lastSyncedAt} />)

    expect(screen.getByText(/Sincronizado às/)).toBeInTheDocument()
  })

  it('não renderiza nada antes da primeira sincronização', () => {
    const { container } = render(<DataFreshness latestDataDate={null} lastSyncedAt={null} />)

    expect(container).toBeEmptyDOMElement()
  })
})
