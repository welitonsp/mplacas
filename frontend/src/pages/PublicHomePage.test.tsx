import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Home from './PublicHomePage'

describe('PublicHomePage — clareza comercial e conversão', () => {
  it('explica a proposta em uma pergunta concreta sobre geração e fatura', () => {
    render(<Home />)

    const headline = screen.getByRole('heading', { level: 1 })
    expect(headline).toHaveTextContent('O que sua usina gera')
    expect(headline).toHaveTextContent('aparece na conta?')
    expect(screen.getByText(/NEPViewer, clima e fatura Equatorial/i)).toBeInTheDocument()
  })

  it('prepara o contato com a equipe sem inventar um formulário ou canal de envio', () => {
    render(<Home />)

    const contact = screen.getAllByRole('link', { name: /avaliar minha usina/i })
      .find((link) => link.classList.contains('header-cta'))
    expect(contact).toBeDefined()
    const href = contact?.getAttribute('href') ?? ''
    expect(href.startsWith('mailto:oi@mplacas.com.br?')).toBe(true)
    expect(href).toContain('Quero%20avaliar%20minha%20usina')
    expect(href).toContain('Portal%20ou%20inversor')
    expect(href).toContain('Cidade%2FUF')
  })

  it('responde às dúvidas principais e mantém conteúdo progressivo em elementos nativos', () => {
    render(<Home />)

    expect(screen.getByText('Quais dados a MPlacas considera?').tagName).toBe('SUMMARY')
    expect(screen.getByText('Os indicadores de energia são calculados por IA?').tagName).toBe('SUMMARY')
    expect(screen.getByText('O que acontece quando faltam dados?').tagName).toBe('SUMMARY')
  })

  it('associa o controle do menu ao elemento de navegação e permite fechar por âncora', () => {
    render(<Home />)

    const toggle = screen.getByRole('button', { name: 'Abrir menu' })
    const nav = screen.getByRole('navigation', { name: 'Navegação principal' })
    expect(toggle).toHaveAttribute('aria-controls', nav.id)
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(screen.getByRole('link', { name: 'Dúvidas' }))
    expect(screen.getByRole('button', { name: 'Abrir menu' })).toHaveAttribute('aria-expanded', 'false')
  })
})
