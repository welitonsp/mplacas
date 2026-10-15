import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { OverviewKpiRail } from './OverviewKpiRail'
import { DASHBOARD_FINANCIAL_PATH, DASHBOARD_PRODUCTION_PATH } from '../routes'

function renderRail(overrides: Partial<Parameters<typeof OverviewKpiRail>[0]> = {}) {
  return render(
    <MemoryRouter>
      <OverviewKpiRail
        cycleProduction={500}
        latestProduction={40}
        latestProductionDate="2026-07-30"
        estimatedSavings={120.4}
        savingsUnavailableReason={null}
        referenceMonth="2026-07"
        {...overrides}
      />
    </MemoryRouter>,
  )
}

describe('OverviewKpiRail', () => {
  it('resume produção, último dado e economia com período explícito', () => {
    renderRail()

    const rail = screen.getByRole('group', { name: 'Resumo executivo do ciclo' })
    const [ciclo, ultimo, desempenho, economia] = within(rail).getAllByRole('link')
    expect(ciclo).toHaveTextContent('Produção do ciclo500kWhMedidoCiclo 2026-07')
    expect(ultimo).toHaveTextContent('40kWh')
    expect(within(rail).getByText('Dado de 30/07/2026')).toBeInTheDocument()
    expect(desempenho).toHaveTextContent('—')
    expect(desempenho).toHaveTextContent('Indisponível')
    expect(desempenho).toHaveTextContent('Sem esperado no recorte')
    expect(economia).toHaveTextContent(/R\$\s*120,40/)
    expect(economia).toHaveTextContent('Estimado')
    expect(within(rail).getAllByText(/2026-07/)).toHaveLength(2)
  })

  it('mostra o desempenho calculado com a quantidade de dias avaliados', () => {
    renderRail({ performancePercent: 88.64, performanceAssessedDays: 2 })

    const desempenho = screen.getAllByRole('link')[2]
    expect(desempenho).toHaveTextContent('88,6%')
    expect(desempenho).toHaveTextContent('Calculado')
    expect(desempenho).toHaveTextContent('2 dias avaliados')
  })

  it('leva produção e financeiro aos módulos correspondentes', () => {
    renderRail()

    const links = screen.getAllByRole('link', { name: /Ver detalhes/ })
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      DASHBOARD_PRODUCTION_PATH,
      DASHBOARD_PRODUCTION_PATH,
      DASHBOARD_PRODUCTION_PATH,
      DASHBOARD_FINANCIAL_PATH,
    ])
  })

  it('carregando ou sem dado não vira "Medido": o selo diz o motivo', () => {
    renderRail({ latestProduction: null, latestProductionDate: null, dailyStatus: 'loading' })

    const ultimo = screen.getAllByRole('link')[1]
    expect(ultimo).toHaveTextContent('—')
    expect(ultimo).toHaveTextContent('Carregando')
    expect(ultimo).not.toHaveTextContent('Medido')
    expect(ultimo).not.toHaveTextContent('kWh')
  })

  it('ciclo com dados parciais marca a produção como "Medido · parcial"', () => {
    renderRail({ cyclePartial: true })

    expect(screen.getAllByRole('link')[0]).toHaveTextContent('Medido · parcial')
  })

  it('não fabrica R$ 0 quando a economia está indisponível e mostra o motivo', () => {
    renderRail({
      estimatedSavings: null,
      savingsUnavailableReason: 'TARIFF_NOT_AVAILABLE',
    })

    const economia = screen.getAllByRole('link')[3]
    expect(economia).toHaveTextContent('Indisponível')
    expect(economia).not.toHaveTextContent('Estimado')
    expect(screen.queryByText(/R\$\s*0,00/)).not.toBeInTheDocument()
    expect(screen.getByText(/não tem a tarifa com impostos registrada/i)).toBeInTheDocument()
  })
})
