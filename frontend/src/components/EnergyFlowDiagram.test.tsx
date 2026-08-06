import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EnergyFlowDiagram } from './EnergyFlowDiagram'

describe('EnergyFlowDiagram', () => {
  it('monta o SankeyFlow com os valores corretos de produção, autoconsumo, injeção e importação', () => {
    render(
      <EnergyFlowDiagram
        production={100}
        selfConsumption={60}
        injected={40}
        imported={20}
        consumption={80}
      />
    )

    const svg = screen.getByRole('img')
    expect(svg).toHaveAttribute(
      'aria-label',
      'Produção de 100 kWh: 60 kWh consumidos diretamente, 40 kWh injetados na rede. Consumo total de 80 kWh: 60 kWh de produção própria, 20 kWh importados da rede.',
    )
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
