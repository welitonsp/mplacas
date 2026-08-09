import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { stubMatchMediaMatches } from '../../test/matchMedia'
import { Gauge } from './Gauge'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Gauge', () => {
  it('desenha strokeDasharray "0 100" quando value=0', async () => {
    const { container } = render(<Gauge value={0} label="Índice de saúde" />)
    const progressCircle = container.querySelectorAll('circle')[1]

    await waitFor(() => {
      expect(progressCircle).toHaveAttribute('stroke-dasharray', '0 100')
    })
  })

  it('desenha strokeDasharray "50 100" quando value=50', async () => {
    const { container } = render(<Gauge value={50} label="Índice de saúde" />)
    const progressCircle = container.querySelectorAll('circle')[1]

    await waitFor(() => {
      expect(progressCircle).toHaveAttribute('stroke-dasharray', '50 100')
    })
  })

  it('desenha strokeDasharray "100 100" quando value=100', async () => {
    const { container } = render(<Gauge value={100} label="Índice de saúde" />)
    const progressCircle = container.querySelectorAll('circle')[1]

    await waitFor(() => {
      expect(progressCircle).toHaveAttribute('stroke-dasharray', '100 100')
    })
  })

  it('clampa valores abaixo de 0 para 0, sem quebrar o SVG', async () => {
    const { container } = render(<Gauge value={-10} label="Índice de saúde" />)
    const progressCircle = container.querySelectorAll('circle')[1]

    await waitFor(() => {
      expect(progressCircle).toHaveAttribute('stroke-dasharray', '0 100')
    })
  })

  it('clampa valores acima de 100 para 100, sem quebrar o SVG', async () => {
    const { container } = render(<Gauge value={150} label="Índice de saúde" />)
    const progressCircle = container.querySelectorAll('circle')[1]

    await waitFor(() => {
      expect(progressCircle).toHaveAttribute('stroke-dasharray', '100 100')
    })
  })

  it('expõe aria-label coerente com o valor exibido', () => {
    render(<Gauge value={82} label="Índice de saúde" />)

    const svg = screen.getByRole('img')
    expect(svg).toHaveAttribute('aria-label', 'Índice de saúde: 82%')
  })

  it('usa valueLabel customizado no aria-label e no centro quando informado', () => {
    render(<Gauge value={82} label="Autonomia" valueLabel="8,2h" />)

    const svg = screen.getByRole('img')
    expect(svg).toHaveAttribute('aria-label', 'Autonomia: 8,2h')
    expect(screen.getByText('8,2h')).toBeInTheDocument()
  })

  it('mostra aria-label sem rótulo quando label não é informado', () => {
    render(<Gauge value={30} />)

    const svg = screen.getByRole('img')
    expect(svg).toHaveAttribute('aria-label', '30% de 100')
  })

  describe('animação de entrada (uma vez por montagem, nunca em refetch)', () => {
    it('o anel nasce em "0 100" e cresce até o valor real após a montagem — texto/aria-label não esperam', async () => {
      const { container } = render(<Gauge value={65} label="Índice de saúde" />)
      const progressCircle = container.querySelectorAll('circle')[1]

      expect(progressCircle).toHaveAttribute('stroke-dasharray', '0 100')
      // O texto central e o aria-label mostram o valor real desde já — só o
      // traço visual do anel começa vazio.
      expect(screen.getByText('65%')).toBeInTheDocument()
      expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'Índice de saúde: 65%')

      await waitFor(() => {
        expect(progressCircle).toHaveAttribute('stroke-dasharray', '65 100')
      })
    })

    it('prefers-reduced-motion: reduce mostra o valor final já no primeiro render, sem animação', () => {
      stubMatchMediaMatches(true)

      const { container } = render(<Gauge value={65} label="Índice de saúde" />)
      const progressCircle = container.querySelectorAll('circle')[1]

      expect(progressCircle).toHaveAttribute('stroke-dasharray', '65 100')
    })

    it('um refetch (rerender com valor novo, sem desmontar) não reanima do zero', async () => {
      const { container, rerender } = render(<Gauge value={65} label="Índice de saúde" />)
      const progressCircle = container.querySelectorAll('circle')[1]

      await waitFor(() => {
        expect(progressCircle).toHaveAttribute('stroke-dasharray', '65 100')
      })

      rerender(<Gauge value={40} label="Índice de saúde" />)

      expect(progressCircle).toHaveAttribute('stroke-dasharray', '40 100')
    })
  })
})
