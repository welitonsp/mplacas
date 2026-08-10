import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PlantSelector } from './PlantSelector'
import { usePlant } from '../contexts/PlantContext'
import type { Plant } from '../lib/dashboard/plant-contracts'

vi.mock('../contexts/PlantContext', () => ({
  usePlant: vi.fn(),
}))

const mockedUsePlant = vi.mocked(usePlant)

const PLANT_A: Plant = { id: 'p1', name: 'Matriz — Telhado A', installedPowerKwp: '48.600' }
const PLANT_B: Plant = { id: 'p2', name: 'Filial Norte', installedPowerKwp: null }

function setPlant(overrides: Partial<ReturnType<typeof usePlant>> = {}) {
  mockedUsePlant.mockReturnValue({
    plantId: null,
    plants: [],
    loading: false,
    error: null,
    selectPlant: vi.fn(),
    ...overrides,
  })
}

describe('PlantSelector', () => {
  it('com mais de uma usina, renderiza um <select> com todas as opções', () => {
    setPlant({ plantId: PLANT_A.id, plants: [PLANT_A, PLANT_B] })
    render(<PlantSelector />)

    const select = screen.getByRole('combobox', { name: /usina ativa/i })
    expect(select).toBeInTheDocument()
    expect(screen.getByRole('option', { name: PLANT_A.name })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: PLANT_B.name })).toBeInTheDocument()
    expect(screen.getByText('48,6 kWp instalados')).toBeInTheDocument()
    expect(select).toHaveAccessibleDescription('48,6 kWp instalados')
  })

  it('trocar a seleção no dropdown chama selectPlant com o id correto', () => {
    const selectPlant = vi.fn()
    setPlant({ plantId: PLANT_A.id, plants: [PLANT_A, PLANT_B], selectPlant })
    render(<PlantSelector />)

    const select = screen.getByRole('combobox', { name: /usina ativa/i })
    fireEvent.change(select, { target: { value: PLANT_B.id } })

    expect(selectPlant).toHaveBeenCalledTimes(1)
    expect(selectPlant).toHaveBeenCalledWith(PLANT_B.id)
  })

  it('o <select> é alcançável por Tab e mostra foco visível', () => {
    setPlant({ plantId: PLANT_A.id, plants: [PLANT_A, PLANT_B] })
    render(<PlantSelector />)

    const select = screen.getByRole('combobox', { name: /usina ativa/i })
    select.focus()
    expect(select).toHaveFocus()
    expect(select.className).toMatch(/focus-visible:ring/)
  })

  it('com exatamente uma usina, renderiza o nome como texto simples, sem dropdown', () => {
    setPlant({ plantId: PLANT_A.id, plants: [PLANT_A] })
    render(<PlantSelector />)

    expect(screen.getByText(PLANT_A.name)).toBeInTheDocument()
    expect(screen.getByText('Usina ativa')).toBeInTheDocument()
    expect(screen.getByText('48,6 kWp instalados')).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(document.querySelector('select')).not.toBeInTheDocument()
  })

  it('fica visível também em viewport móvel, sem classe hidden no chip operacional', () => {
    setPlant({ plantId: PLANT_A.id, plants: [PLANT_A, PLANT_B] })
    render(<PlantSelector />)

    const chip = screen.getByRole('combobox', { name: /usina ativa/i }).closest('span')?.parentElement
    expect(chip?.className).not.toMatch(/\bhidden\b/)
    expect(chip?.className).toMatch(/\bflex\b/)
  })

  it('com zero usinas, não renderiza nada visível', () => {
    setPlant({ plantId: null, plants: [] })
    const { container } = render(<PlantSelector />)

    expect(container).toBeEmptyDOMElement()
  })
})
