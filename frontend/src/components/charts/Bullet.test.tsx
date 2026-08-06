import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Bullet } from './Bullet'

describe('Bullet', () => {
  it('desenha a barra do valor real proporcional a max', () => {
    render(<Bullet value={50} target={null} max={100} label="Produção" />)

    const bar = screen.getByRole('img')
    const fill = bar.firstElementChild as HTMLElement
    expect(fill.style.width).toBe('50%')
  })

  it('posiciona o tick de meta na proporção correta de max', () => {
    render(<Bullet value={50} target={80} max={100} label="Produção" />)

    const tick = screen.getByTestId('bullet-target-tick')
    expect(tick.style.left).toBe('80%')
  })

  it('não desenha tick quando target é null (sem meta disponível)', () => {
    render(<Bullet value={50} target={null} max={100} label="Produção" />)

    expect(screen.queryByTestId('bullet-target-tick')).not.toBeInTheDocument()
  })

  it('não fabrica meta/desvio quando target é null — mostra só a barra real', () => {
    render(
      <Bullet
        value={543.6}
        target={null}
        label="Produção do ciclo"
        valueFormatter={(n) => `${n} kWh`}
      />,
    )

    const bar = screen.getByRole('img')
    expect(bar).toHaveAttribute('aria-label', 'Produção do ciclo: 543.6 kWh')
    expect(screen.queryByTestId('bullet-target-tick')).not.toBeInTheDocument()
  })

  it('calcula escala automática (max implícito) quando max não é informado', () => {
    render(<Bullet value={50} target={80} label="Produção" />)

    // naturalMax = max(50, 80) * 1.2 = 96 -> tick de 80 fica em ~83.3%
    const tick = screen.getByTestId('bullet-target-tick')
    const leftPct = Number.parseFloat(tick.style.left)
    expect(leftPct).toBeGreaterThan(80)
    expect(leftPct).toBeLessThan(90)
  })

  it('expõe aria-label completo com valor, meta e desvio percentual', () => {
    render(
      <Bullet
        value={543.6}
        target={580}
        max={700}
        label="Produção do ciclo"
        valueFormatter={(n) => `${n} kWh`}
      />,
    )

    const bar = screen.getByRole('img')
    expect(bar).toHaveAttribute(
      'aria-label',
      'Produção do ciclo: 543.6 kWh, esperado 580 kWh — 6,3% abaixo do esperado',
    )
  })

  it('calcula desvio positivo (acima do esperado) corretamente', () => {
    render(<Bullet value={120} target={100} max={200} valueFormatter={(n) => `${n}`} />)

    const bar = screen.getByRole('img')
    expect(bar.getAttribute('aria-label')).toContain('20% acima do esperado')
    expect(screen.getByText('+20%')).toBeInTheDocument()
  })

  it('clampa a largura da barra em 100% quando value excede max explícito', () => {
    render(<Bullet value={250} target={100} max={200} />)

    const bar = screen.getByRole('img')
    const fill = bar.firstElementChild as HTMLElement
    expect(fill.style.width).toBe('100%')
  })

  it('trata target=0 sem calcular desvio (divisão por zero)', () => {
    render(<Bullet value={10} target={0} max={100} valueFormatter={(n) => `${n} kWh`} />)

    const bar = screen.getByRole('img')
    expect(bar).toHaveAttribute('aria-label', '10 kWh, esperado 0 kWh')
  })
})
