import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EnergyFlowDiagram } from './EnergyFlowDiagram'

describe('EnergyFlowDiagram', () => {
  it('expõe as duas barras de fluxo (produção e consumo) com semântica ARIA de progressbar', () => {
    render(
      <EnergyFlowDiagram
        production={100}
        selfConsumption={60}
        injected={40}
        imported={20}
        consumption={80}
      />
    )

    const progressbars = screen.getAllByRole('progressbar')
    expect(progressbars).toHaveLength(2)
    progressbars.forEach((bar) => {
      expect(bar).toHaveAttribute('aria-valuemin', '0')
      expect(bar).toHaveAttribute('aria-valuemax', '100')
      expect(bar).toHaveAttribute('aria-valuenow')
    })
  })

  it('não renderiza barras quando não há dados suficientes', () => {
    render(
      <EnergyFlowDiagram
        production={null}
        selfConsumption={null}
        injected={null}
        imported={null}
        consumption={null}
      />
    )

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
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
