import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Card } from './Card'

describe('Card', () => {
  it('renderiza com o esqueleto padrão (fundo branco, borda cinza sutil, cantos arredondados)', () => {
    render(<Card>conteúdo</Card>)

    const card = screen.getByText('conteúdo')
    expect(card.className).toMatch(/rounded-\[var\(--radius-card\)\]/)
    expect(card.className).toMatch(/border-\[var\(--color-border\)\]/)
    expect(card.className).toMatch(/bg-\[var\(--color-surface\)\]/)
    expect(card.className).not.toMatch(/border-dashed/)
  })

  it('aplica borda tracejada quando dashed=true, sem herdar cor de aviso por padrão', () => {
    render(<Card dashed>conteúdo</Card>)

    const card = screen.getByText('conteúdo')
    expect(card.className).toMatch(/border-dashed/)
    expect(card.className).toMatch(/border-\[var\(--color-border\)\]/)
  })

  it('tone="warning" usa os tokens de aviso, não cor cinza/vermelho crua', () => {
    render(<Card tone="warning">conteúdo</Card>)

    const card = screen.getByText('conteúdo')
    expect(card.className).toMatch(/--color-warning-light/)
    expect(card.className).toMatch(/--color-warning/)
  })

  it('tone="danger" usa os tokens de alerta, não classes bg-red-*/border-red-*', () => {
    render(<Card tone="danger">conteúdo</Card>)

    const card = screen.getByText('conteúdo')
    expect(card.className).toMatch(/--color-danger-light/)
    expect(card.className).not.toMatch(/bg-red-|border-red-/)
  })

  it('nunca desenha faixa lateral colorida (ADR-077, decisão 18: estado só no texto/ícone)', () => {
    for (const tone of ['neutral', 'warning', 'danger'] as const) {
      const { unmount } = render(<Card tone={tone}>conteúdo</Card>)
      expect(screen.getByText('conteúdo').className).not.toMatch(/border-l-\d|border-l-\[/)
      unmount()
    }
  })

  it('className extra é preservado junto do esqueleto padrão', () => {
    render(<Card className="mt-4">conteúdo</Card>)

    const card = screen.getByText('conteúdo')
    expect(card.className).toMatch(/mt-4/)
    expect(card.className).toMatch(/rounded-\[var\(--radius-card\)\]/)
  })
})

// Guarda de código-fonte (mesmo padrão de `typography.test.tsx`): a faixa
// lateral colorida saiu de `Card` e de `DiagnosticsCard`; nenhum componente ou
// página deve reintroduzi-la por classe solta (ADR-077, decisão 18).
const sideStripeSources = import.meta.glob(['./**/*.tsx', '../pages/**/*.tsx', '../lib/dashboard/visuals.ts'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

describe('nenhum componente usa faixa lateral colorida', () => {
  it.each(Object.entries(sideStripeSources).filter(([path]) => !path.includes('.test.')))(
    '%s não usa border-l-N/border-l-[cor]',
    (_path, content) => {
      expect(content.match(/\bborder-l-(?:\d|\[)/g) ?? []).toEqual([])
    }
  )
})
