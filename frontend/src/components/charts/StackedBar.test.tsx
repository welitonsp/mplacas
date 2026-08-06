import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StackedBar } from './StackedBar'

describe('StackedBar', () => {
  it('calcula larguras proporcionais ao total (implícito pela soma dos segmentos)', () => {
    render(
      <StackedBar
        segments={[
          { label: 'Autossuficiência', value: 77.7, tone: 'success' },
          { label: 'Dependência da rede', value: 22.3, tone: 'neutral' },
        ]}
        valueFormatter={(value) => `${value}%`}
      />,
    )

    const bar = screen.getByRole('img')
    const fills = bar.children
    expect(fills).toHaveLength(2)
    expect((fills[0] as HTMLElement).style.width).toBe('77.7%')
    expect((fills[1] as HTMLElement).style.width).toBe('22.3%')
  })

  it('calcula larguras proporcionais a um total explícito', () => {
    render(
      <StackedBar
        segments={[{ label: 'Energia', value: 50 }]}
        total={200}
        valueFormatter={(value) => `R$ ${value}`}
      />,
    )

    const bar = screen.getByRole('img')
    expect((bar.children[0] as HTMLElement).style.width).toBe('25%')
  })

  it('não renderiza segmento com value <= 0', () => {
    render(
      <StackedBar
        segments={[
          { label: 'Energia', value: 50 },
          { label: 'Outros', value: 0 },
          { label: 'Negativo', value: -5 },
        ]}
        valueFormatter={(value) => `R$ ${value}`}
      />,
    )

    const bar = screen.getByRole('img')
    // Só o segmento com valor positivo vira um traço na barra.
    expect(bar.children).toHaveLength(1)
    // A legenda continua listando todos os segmentos recebidos.
    expect(screen.getByText('Outros')).toBeInTheDocument()
    expect(screen.getByText('Negativo')).toBeInTheDocument()
  })

  it('não quebra quando o total efetivo é 0 ou negativo', () => {
    render(
      <StackedBar
        segments={[
          { label: 'A', value: 0 },
          { label: 'B', value: 0 },
        ]}
        valueFormatter={(value) => `R$ ${value}`}
      />,
    )

    const bar = screen.getByRole('img')
    expect(bar.children).toHaveLength(0)
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
  })

  it('expõe aria-label resumindo a composição com valores formatados', () => {
    render(
      <StackedBar
        segments={[
          { label: 'energia', value: 47.72 },
          { label: 'iluminação pública', value: 30.21 },
        ]}
        total={77.93}
        valueFormatter={(value) => `R$ ${value.toFixed(2)}`}
      />,
    )

    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      'Total R$ 77.93: energia R$ 47.72, iluminação pública R$ 30.21',
    )
  })

  it('legenda mostra cor, rótulo e valor formatado de cada segmento', () => {
    render(
      <StackedBar
        segments={[
          { label: 'Autossuficiência', value: 77.7, tone: 'success' },
          { label: 'Dependência da rede', value: 22.3, tone: 'neutral' },
        ]}
        valueFormatter={(value) => `${value}%`}
      />,
    )

    expect(screen.getByText('Autossuficiência')).toBeInTheDocument()
    expect(screen.getByText('77.7%')).toBeInTheDocument()
    expect(screen.getByText('Dependência da rede')).toBeInTheDocument()
    expect(screen.getByText('22.3%')).toBeInTheDocument()
  })

  it('não quebra e mostra mensagem quando a lista de segmentos está vazia', () => {
    render(<StackedBar segments={[]} />)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('Nenhum dado para exibir.')).toBeInTheDocument()
  })
})
