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
    expect(within(rail).getByText('500 kWh')).toBeInTheDocument()
    expect(within(rail).getByText('40 kWh')).toBeInTheDocument()
    expect(within(rail).getByText(/R\$\s*120,40/)).toBeInTheDocument()
    expect(within(rail).getByText('Dado de 30/07/2026')).toBeInTheDocument()
    expect(within(rail).getAllByText(/2026-07/)).toHaveLength(2)
  })

  it('leva produção e financeiro aos módulos correspondentes', () => {
    renderRail()

    const links = screen.getAllByRole('link', { name: /Ver detalhes/ })
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      DASHBOARD_PRODUCTION_PATH,
      DASHBOARD_PRODUCTION_PATH,
      DASHBOARD_FINANCIAL_PATH,
    ])
  })

  it('não fabrica R$ 0 quando a economia está indisponível e mostra o motivo', () => {
    renderRail({
      estimatedSavings: null,
      savingsUnavailableReason: 'TARIFF_NOT_AVAILABLE',
    })

    expect(screen.getByText('Indisponível')).toBeInTheDocument()
    expect(screen.queryByText(/R\$\s*0,00/)).not.toBeInTheDocument()
    expect(screen.getByText(/não tem a tarifa com impostos registrada/i)).toBeInTheDocument()
  })
})
