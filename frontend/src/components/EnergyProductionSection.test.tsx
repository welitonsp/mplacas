import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { EnergyProductionSection } from './EnergyProductionSection'
import type { CycleQuality, ExecutiveIndicators } from '../lib/dashboard/contracts'

function buildIndicators(overrides: Partial<ExecutiveIndicators> = {}): ExecutiveIndicators {
  return {
    cycle_production_kwh: 500,
    imported_kwh: 120,
    injected_kwh: 80,
    estimated_self_consumption_kwh: 420,
    estimated_total_consumption_kwh: 540,
    self_consumption_rate_percent: 84,
    self_sufficiency_rate_percent: 77.7,
    grid_dependency_rate_percent: 22.3,
    exported_generation_rate_percent: 16,
    credit_coverage_rate_percent: 100,
    bill_energy_component_brl: 350.5,
    health_score: 90,
    ...overrides,
  }
}

function buildQuality(overrides: Partial<CycleQuality> = {}): CycleQuality {
  return { missing_days: 0, provisional_days: 0, incomplete_days: 0, unavailable_days: 0, ...overrides }
}

function cardFor(label: string): HTMLElement {
  const labelNode = screen.getByText(label)
  const card = labelNode.closest('div')
  if (!card) throw new Error(`card não encontrado para o rótulo ${label}`)
  return card
}

describe('EnergyProductionSection', () => {
  it('não mostra selo "Parcial" em nenhum card quando o ciclo está consolidado', () => {
    render(<EnergyProductionSection indicators={buildIndicators()} quality={buildQuality()} />)

    expect(screen.queryByText('Parcial')).not.toBeInTheDocument()
  })

  it('marca "Parcial" apenas nos cards derivados do dado diário de geração, nunca em importada/injetada', () => {
    // "Produção no ciclo" saiu deste componente na Etapa 5 (agora fica em
    // `DashboardPage`, ao lado de "Produção esperada") — a mesma regra de
    // completude (`hasIncompleteDailyProduction`, exportada por este arquivo)
    // continua sendo aplicada lá, só que fora deste teste de unidade.
    const quality = buildQuality({ missing_days: 3 })
    render(<EnergyProductionSection indicators={buildIndicators()} quality={quality} />)

    expect(within(cardFor('Autoconsumo estimado')).getByText('Parcial')).toBeInTheDocument()
    expect(within(cardFor('Consumo total estimado')).getByText('Parcial')).toBeInTheDocument()

    // `imported_kwh`/`injected_kwh` vêm da fatura confirmada, não do dado diário —
    // nunca devem receber o selo, mesmo com `missing_days` no ciclo.
    expect(within(cardFor('Energia importada')).queryByText('Parcial')).not.toBeInTheDocument()
    expect(within(cardFor('Energia injetada')).queryByText('Parcial')).not.toBeInTheDocument()
  })
})
