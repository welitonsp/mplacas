import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Card } from './Card'

describe('Card', () => {
  it('renderiza com o esqueleto padrão (fundo branco, borda cinza sutil, cantos arredondados)', () => {
    render(<Card>conteúdo</Card>)

    const card = screen.getByText('conteúdo')
    expect(card.className).toMatch(/rounded-xl/)
    expect(card.className).toMatch(/border-gray-200/)
    expect(card.className).toMatch(/bg-white/)
    expect(card.className).not.toMatch(/border-dashed/)
  })

  it('aplica borda tracejada quando dashed=true, sem herdar cor de aviso por padrão', () => {
    render(<Card dashed>conteúdo</Card>)

    const card = screen.getByText('conteúdo')
    expect(card.className).toMatch(/border-dashed/)
    expect(card.className).toMatch(/border-gray-200/)
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

  it('accent adiciona borda esquerda de severidade sem alterar o fundo', () => {
    render(<Card accent="success">conteúdo</Card>)

    const card = screen.getByText('conteúdo')
    expect(card.className).toMatch(/border-l-4/)
    expect(card.className).toMatch(/bg-white/)
  })

  it('className extra é preservado junto do esqueleto padrão', () => {
    render(<Card className="mt-4">conteúdo</Card>)

    const card = screen.getByText('conteúdo')
    expect(card.className).toMatch(/mt-4/)
    expect(card.className).toMatch(/rounded-xl/)
  })
})
