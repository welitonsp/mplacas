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

  it('leva cada card de capacidade ao aprofundamento correspondente', () => {
    render(<Home />)

    expect(screen.getByRole('link', { name: 'Saiba mais sobre Telemetria consolidada' })).toHaveAttribute('href', '#como-funciona')
    expect(screen.getByRole('link', { name: 'Saiba mais sobre Diagnóstico determinístico' })).toHaveAttribute('href', '#confiabilidade')
    expect(screen.getByRole('link', { name: 'Saiba mais sobre Relatório auditável' })).toHaveAttribute('href', '#duvidas')
  })

  it('associa o controle do menu à navegação e encaminha o foco para o primeiro link ao abrir', () => {
    render(<Home />)

    const toggle = screen.getByRole('button', { name: 'Abrir menu' })
    const nav = screen.getByRole('navigation', { name: 'Navegação principal' })
    expect(toggle).toHaveAttribute('aria-controls', nav.id)
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('link', { name: 'Como funciona' })).toHaveFocus()
    fireEvent.click(screen.getByRole('link', { name: 'Dúvidas' }))
    expect(screen.getByRole('button', { name: 'Abrir menu' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('fecha o menu com Escape e devolve o foco ao controle', () => {
    render(<Home />)

    const toggle = screen.getByRole('button', { name: 'Abrir menu' })
    fireEvent.click(toggle)
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.getByRole('button', { name: 'Abrir menu' })).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveFocus()
  })

  it('oferece atalho de teclado para o conteúdo principal e alvo de toque confortável no menu', () => {
    const { container } = render(<Home />)

    const skip = screen.getByRole('link', { name: 'Pular para o conteúdo' })
    expect(skip).toHaveAttribute('href', '#main-content')
    expect(container.querySelector('main#main-content')).toBeInTheDocument()

    const toggle = screen.getByRole('button', { name: 'Abrir menu' })
    expect(toggle.className).toContain('menu-toggle')
  })
})
