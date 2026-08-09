import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { stubMatchMediaMatches } from '../../test/matchMedia'
import { BarList } from './BarList'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('BarList', () => {
  it('renderiza uma barra para cada item da lista', () => {
    render(
      <BarList
        items={[
          { label: 'Inversor A', value: 10 },
          { label: 'Inversor B', value: 20 },
          { label: 'Inversor C', value: 30 },
        ]}
      />,
    )

    expect(screen.getAllByRole('progressbar')).toHaveLength(3)
  })

  it('calcula larguras proporcionais ao maior valor da lista quando maxValue não é informado', async () => {
    render(
      <BarList
        items={[
          { label: 'A', value: 25 },
          { label: 'B', value: 100 },
          { label: 'C', value: 50 },
        ]}
      />,
    )

    const bars = screen.getAllByRole('progressbar')

    // A largura final só chega depois do tick de animação de entrada (ver
    // `useChartEntrance`/`ChartEntrance.entrance.test.tsx`) — o primeiro
    // render mostra 0%, que não é o que este teste quer verificar.
    await waitFor(() => {
      const fillWidths = bars.map((bar) => (bar.firstElementChild as HTMLElement).style.width)
      expect(fillWidths).toEqual(['25%', '100%', '50%'])
    })
  })

  it('calcula larguras proporcionais a maxValue explícito quando informado', async () => {
    render(<BarList items={[{ label: 'A', value: 40 }]} maxValue={200} />)

    const bar = screen.getByRole('progressbar')
    const fill = bar.firstElementChild as HTMLElement

    await waitFor(() => {
      expect(fill.style.width).toBe('20%')
    })
  })

  it('expõe role progressbar com atributos ARIA corretos em cada item', () => {
    render(<BarList items={[{ label: 'Autossuficiência', value: 70 }]} maxValue={100} />)

    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '70')
    expect(bar).toHaveAttribute('aria-valuemin', '0')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(bar).toHaveAttribute('aria-label', 'Autossuficiência: 70')
  })

  it('usa valueFormatter para formatar o valor exibido e no aria-label', () => {
    render(
      <BarList
        items={[{ label: 'Perda por sujeira', value: 12.345 }]}
        valueFormatter={(value) => `${value.toFixed(1)}%`}
      />,
    )

    expect(screen.getByText('12.3%')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute(
      'aria-label',
      'Perda por sujeira: 12.3%',
    )
  })

  it('não quebra e não renderiza barras quando a lista está vazia', () => {
    render(<BarList items={[]} />)

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('trata valor negativo/maxValue inválido sem quebrar (largura 0)', () => {
    render(<BarList items={[{ label: 'A', value: -5 }]} maxValue={0} />)

    const bar = screen.getByRole('progressbar')
    const fill = bar.firstElementChild as HTMLElement

    expect(fill.style.width).toBe('0%')
  })

  it('não fabrica barra de 0% para item com value=null — mostra estado neutro', () => {
    render(
      <BarList
        items={[
          { label: 'Degradação', value: null },
          { label: 'Sujeira', value: 10 },
        ]}
      />,
    )

    // Só o item com valor numérico vira progressbar.
    expect(screen.getAllByRole('progressbar')).toHaveLength(1)

    const placeholder = screen.getByRole('status')
    expect(placeholder).toHaveAttribute('aria-label', 'Degradação: —')
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('itens com value=null não entram no cálculo do maior valor (maxValue implícito)', async () => {
    render(
      <BarList
        items={[
          { label: 'A', value: null },
          { label: 'B', value: 40 },
        ]}
      />,
    )

    const bar = screen.getByRole('progressbar')
    const fill = bar.firstElementChild as HTMLElement

    await waitFor(() => {
      expect(fill.style.width).toBe('100%')
    })
  })

  describe('animação de entrada (uma vez por montagem, nunca em refetch)', () => {
    it('a barra nasce em 0% e cresce até o valor real após a montagem', async () => {
      render(<BarList items={[{ label: 'A', value: 60 }]} maxValue={100} />)

      const bar = screen.getByRole('progressbar')
      const fill = bar.firstElementChild as HTMLElement

      expect(fill.style.width).toBe('0%')

      await waitFor(() => {
        expect(fill.style.width).toBe('60%')
      })
    })

    it('prefers-reduced-motion: reduce mostra a largura final já no primeiro render, sem animação', () => {
      stubMatchMediaMatches(true)

      render(<BarList items={[{ label: 'A', value: 60 }]} maxValue={100} />)

      const bar = screen.getByRole('progressbar')
      const fill = bar.firstElementChild as HTMLElement

      expect(fill.style.width).toBe('60%')
    })

    it('um refetch (rerender com valor novo, sem desmontar) não reanima do zero', async () => {
      const { rerender } = render(<BarList items={[{ label: 'A', value: 60 }]} maxValue={100} />)

      const getFill = () => (screen.getByRole('progressbar').firstElementChild as HTMLElement)

      await waitFor(() => {
        expect(getFill().style.width).toBe('60%')
      })

      // Mesma instância (nenhum unmount) recebendo um valor novo, como um
      // `usePlantResource.refetch()` traria para a mesma usina.
      rerender(<BarList items={[{ label: 'A', value: 90 }]} maxValue={100} />)

      // Nunca passa por 0% de novo — vai direto pro novo valor (a pequena
      // transição de 60% -> 90% já existente, não uma reanimação do zero).
      expect(getFill().style.width).toBe('90%')
    })
  })
})
