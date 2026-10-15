import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EnergyFlowDiagram } from './EnergyFlowDiagram'

describe('EnergyFlowDiagram', () => {
  it('monta as duas barras de composição com os valores de produção, autoconsumo, injeção e importação', () => {
    render(
      <EnergyFlowDiagram
        production={100}
        selfConsumption={60}
        injected={40}
        imported={20}
        consumption={80}
      />
    )

    const [producao, consumo] = screen.getAllByRole('img')
    expect(producao).toHaveAttribute(
      'aria-label',
      'Produção de 100 kWh: 60 kWh consumidos diretamente, 40 kWh injetados na rede.',
    )
    expect(consumo).toHaveAttribute(
      'aria-label',
      'Consumo estimado total de 80 kWh: 60 kWh de produção própria, 20 kWh importados da rede.',
    )
    // Autoconsumo é inferido pelo motor: o qualificador nunca pode sumir.
    expect(screen.getByText('Consumida na casa (estimado)')).toBeInTheDocument()
    expect(document.body).toHaveTextContent('De onde veio o consumo (estimado)')
    // O antigo nó "Rede" (injetado + importado = 60) não existe na fatura.
    expect(screen.queryByText('Rede')).not.toBeInTheDocument()
  })

  it('não renderiza o diagrama quando não há dados suficientes', () => {
    render(
      <EnergyFlowDiagram
        production={null}
        selfConsumption={null}
        injected={null}
        imported={null}
        consumption={null}
      />
    )

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('Dados insuficientes para o diagrama.')).toBeInTheDocument()
  })

  it('mostra o selo "Parcial" quando o ciclo tem dado diário incompleto (Etapa 3.3, absorve o selo dos cards removidos)', () => {
    render(
      <EnergyFlowDiagram
        production={100}
        selfConsumption={60}
        injected={40}
        imported={20}
        consumption={80}
        partial
      />
    )

    expect(screen.getByText('Parcial')).toBeInTheDocument()
  })

  it('não mostra o selo "Parcial" quando o ciclo está completo', () => {
    render(
      <EnergyFlowDiagram
        production={100}
        selfConsumption={60}
        injected={40}
        imported={20}
        consumption={80}
      />
    )

    expect(screen.queryByText('Parcial')).not.toBeInTheDocument()
  })
})
