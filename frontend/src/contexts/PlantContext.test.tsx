import { describe, expect, it, vi, beforeEach } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import type { Plant } from '../lib/dashboard/plant-contracts'

const P1: Plant = { id: '11111111-1111-1111-1111-111111111111', name: 'Matriz — Telhado A', installedPowerKwp: '48.600' }
const P2: Plant = { id: '22222222-2222-2222-2222-222222222222', name: 'Filial Norte', installedPowerKwp: null }

const STORAGE_KEY = 'mplacas_selected_plant_v1'

function mockFetchPlants(plants: Plant[]) {
  vi.doMock('../lib/api', () => ({
    fetchPlants: vi.fn(async () => plants),
  }))
}

// Componente mínimo que expõe o valor do contexto para asserção nos testes,
// evitando depender de uma UI de seletor que ainda não existe (Etapa D).
function Probe() {
  return null
}

async function renderWithPlantProvider(initialEntry = '/dashboard') {
  const { PlantProvider, usePlant } = await import('./PlantContext')

  function Consumer() {
    const ctx = usePlant()
    return (
      <div>
        <span data-testid="plantId">{ctx.plantId ?? 'null'}</span>
        <span data-testid="loading">{String(ctx.loading)}</span>
        <span data-testid="error">{ctx.error ?? 'null'}</span>
        <span data-testid="count">{ctx.plants.length}</span>
        <button onClick={() => ctx.selectPlant(P2.id)}>select-p2</button>
        <button onClick={() => ctx.selectPlant(P1.id)}>select-p1</button>
      </div>
    )
  }

  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <PlantProvider>
        <Consumer />
        <Probe />
      </PlantProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.resetModules()
  window.localStorage.clear()
})

describe('PlantContext — precedência de seleção (ADR-069, seção 5)', () => {
  it('usa a usina da query string quando válida (presente na lista)', async () => {
    mockFetchPlants([P1, P2])
    await renderWithPlantProvider(`/dashboard?plant=${P2.id}`)

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('plantId')).toHaveTextContent(P2.id)
  })

  it('cai para o localStorage quando a query string é inválida (fora do escopo)', async () => {
    mockFetchPlants([P1, P2])
    window.localStorage.setItem(STORAGE_KEY, P2.id)

    await renderWithPlantProvider('/dashboard?plant=nao-existe')

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('plantId')).toHaveTextContent(P2.id)
  })

  it('cai para o primeiro item quando o localStorage também é inválido', async () => {
    mockFetchPlants([P1, P2])
    window.localStorage.setItem(STORAGE_KEY, 'nao-existe-tambem')

    await renderWithPlantProvider('/dashboard?plant=tambem-nao-existe')

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('plantId')).toHaveTextContent(P1.id)
  })

  it('usa o primeiro item quando nada está definido (sem query string, sem localStorage)', async () => {
    mockFetchPlants([P1, P2])

    await renderWithPlantProvider('/dashboard')

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('plantId')).toHaveTextContent(P1.id)
  })
})

describe('PlantContext — seleção fora do escopo é descartada silenciosamente', () => {
  it('nunca expõe erro visível quando a query string aponta para usina fora do escopo', async () => {
    mockFetchPlants([P1, P2])

    await renderWithPlantProvider(`/dashboard?plant=00000000-0000-0000-0000-000000000099`)

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('error')).toHaveTextContent('null')
    expect(screen.getByTestId('plantId')).toHaveTextContent(P1.id)
  })
})

describe('PlantContext — selectPlant', () => {
  it('atualiza a query string e o localStorage', async () => {
    mockFetchPlants([P1, P2])

    await renderWithPlantProvider('/dashboard')
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('plantId')).toHaveTextContent(P1.id)

    await act(async () => {
      screen.getByRole('button', { name: 'select-p2' }).click()
    })

    expect(screen.getByTestId('plantId')).toHaveTextContent(P2.id)
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(P2.id)
  })
})

describe('PlantContext — count == 0', () => {
  it('expõe estado vazio sem crash quando a organização não tem usinas', async () => {
    mockFetchPlants([])

    await renderWithPlantProvider('/dashboard')

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('plantId')).toHaveTextContent('null')
    expect(screen.getByTestId('count')).toHaveTextContent('0')
    expect(screen.getByTestId('error')).toHaveTextContent('null')
  })
})

describe('PlantContext — count == 1', () => {
  it('resolve automaticamente para a única usina existente', async () => {
    mockFetchPlants([P1])

    await renderWithPlantProvider('/dashboard')

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('plantId')).toHaveTextContent(P1.id)
    expect(screen.getByTestId('count')).toHaveTextContent('1')
  })
})

describe('PlantContext — falha ao buscar /plants', () => {
  it('expõe o erro e plantId nulo, sem crash', async () => {
    vi.doMock('../lib/api', () => ({
      fetchPlants: vi.fn(async () => {
        throw new Error('Erro ao buscar usinas (500).')
      }),
    }))

    await renderWithPlantProvider('/dashboard')

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('error')).toHaveTextContent('Erro ao buscar usinas (500).')
    expect(screen.getByTestId('plantId')).toHaveTextContent('null')
  })
})
