import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { jsonResponse, singlePlant } from '../../test/dashboardFixtures'

vi.mock('../../env', () => ({
  API_URL: 'https://api.example.test',
}))

const ITEM_KEYS = [
  'LOCATION',
  'DC_CAPACITY',
  'COMMISSIONED_ON',
  'ORIENTATION',
  'MODULE_TECHNOLOGY',
  'INVESTMENT',
  'CONFIRMED_BILL',
]

function setupPayload(overrides: Record<string, unknown> = {}, done: string[] = []) {
  return {
    plant_id: singlePlant.id,
    name: 'Casa do Lago',
    technical: {
      plant_id: singlePlant.id,
      dc_capacity_kwp: null,
      ac_capacity_kw: null,
      array_tilt_degrees: null,
      array_azimuth_degrees: null,
      module_technology: null,
      commissioned_on: null,
      devices: [],
    },
    latitude: null,
    longitude: null,
    financial: { plant_id: singlePlant.id, investment_amount_brl: null, investment_recorded_on: null },
    confirmed_bills: 0,
    pending_bills: 0,
    items: ITEM_KEYS.map((key) => ({ key, done: done.includes(key) })),
    completed: done.length,
    total: ITEM_KEYS.length,
    ...overrides,
  }
}

interface Mocks {
  fetchPlantSetup?: ReturnType<typeof vi.fn>
  updateTechnicalConfiguration?: ReturnType<typeof vi.fn>
  updatePlantLocation?: ReturnType<typeof vi.fn>
  updateFinancialConfiguration?: ReturnType<typeof vi.fn>
}

function installApiMock(mocks: Mocks = {}) {
  const resolved = {
    fetchPlantSetup: mocks.fetchPlantSetup ?? vi.fn(async () => jsonResponse(setupPayload())),
    updateTechnicalConfiguration: mocks.updateTechnicalConfiguration ?? vi.fn(async () => jsonResponse({})),
    updatePlantLocation: mocks.updatePlantLocation ?? vi.fn(async () => jsonResponse({})),
    updateFinancialConfiguration: mocks.updateFinancialConfiguration ?? vi.fn(async () => jsonResponse({})),
  }
  vi.doMock('../../lib/api', () => ({
    ...resolved,
    fetchPlants: vi.fn(async () => [singlePlant]),
    configureApi: vi.fn(),
  }))
  return resolved
}

async function renderPage() {
  const { PlantSetupPage } = await import('./PlantSetupPage')
  const { renderModule } = await import('../../test/renderModule')
  const { DASHBOARD_SETUP_PATH } = await import('../../routes')
  return renderModule(<PlantSetupPage />, DASHBOARD_SETUP_PATH)
}

describe('PlantSetupPage — o cliente informa os dados da usina', () => {
  it('mostra o progresso e o que cada item pendente libera, com atalho para informar', async () => {
    vi.resetModules()
    installApiMock({
      fetchPlantSetup: vi.fn(async () => jsonResponse(setupPayload({}, ['LOCATION', 'INVESTMENT']))),
    })

    await renderPage()

    expect(await screen.findByText('2 de 7 itens informados')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Progresso do cadastro' })).toHaveAttribute('aria-valuenow', '2')
    const list = screen.getByRole('list', { name: 'Itens do cadastro' })
    expect(within(list).getByText('Localização da usina')).toBeInTheDocument()
    expect(within(list).getByText(/Retorno do investimento e quantos meses/)).toBeInTheDocument()
    // 5 pendentes = 5 atalhos "Informar"; os 2 feitos não têm.
    expect(within(list).getAllByRole('link', { name: 'Informar' })).toHaveLength(5)
    expect(screen.getByText(/Informe os dados de Casa do Lago/)).toBeInTheDocument()
  })

  it('salva a instalação enviando só o que mudou, com vírgula decimal convertida e mês virando data', async () => {
    vi.resetModules()
    const fetchPlantSetup = vi.fn(async () => jsonResponse(setupPayload()))
    const updateTechnicalConfiguration = vi.fn(async () => jsonResponse({}))
    installApiMock({ fetchPlantSetup, updateTechnicalConfiguration })

    await renderPage()
    await screen.findByText('0 de 7 itens informados')

    fireEvent.change(screen.getByLabelText('Mês em que a usina foi ligada'), { target: { value: '2025-09' } })
    fireEvent.change(screen.getByLabelText('Potência das placas (kWp)'), { target: { value: '4,4' } })
    fireEvent.change(screen.getByLabelText('Tecnologia das placas'), {
      target: { value: 'MONOCRYSTALLINE_SILICON' },
    })
    fireEvent.change(screen.getByLabelText('Para onde as placas estão viradas'), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar instalação' }))

    await waitFor(() =>
      expect(updateTechnicalConfiguration).toHaveBeenCalledWith(singlePlant.id, {
        commissioned_on: '2025-09-01',
        dc_capacity_kwp: '4.4',
        array_azimuth_degrees: '0',
        module_technology: 'MONOCRYSTALLINE_SILICON',
      }),
    )
    expect(await screen.findByText('Dados da instalação salvos.')).toBeInTheDocument()
    await waitFor(() => expect(fetchPlantSetup).toHaveBeenCalledTimes(2))
  })

  it('Norte (0°) e placa deitada (0°) contam como valor informado, não como "nada mudou"', async () => {
    vi.resetModules()
    const updateTechnicalConfiguration = vi.fn(async () => jsonResponse({}))
    installApiMock({ updateTechnicalConfiguration })

    await renderPage()
    await screen.findByText('0 de 7 itens informados')
    fireEvent.change(screen.getByLabelText('Inclinação das placas (graus)'), { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText('Para onde as placas estão viradas'), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar instalação' }))

    await waitFor(() =>
      expect(updateTechnicalConfiguration).toHaveBeenCalledWith(singlePlant.id, {
        array_tilt_degrees: '0',
        array_azimuth_degrees: '0',
      }),
    )
  })

  it('recusa mês de ligação no futuro sem chamar a API', async () => {
    vi.resetModules()
    const updateTechnicalConfiguration = vi.fn(async () => jsonResponse({}))
    installApiMock({ updateTechnicalConfiguration })

    await renderPage()
    await screen.findByText('0 de 7 itens informados')
    fireEvent.change(screen.getByLabelText('Mês em que a usina foi ligada'), { target: { value: '2999-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar instalação' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('não pode estar no futuro')
    expect(updateTechnicalConfiguration).not.toHaveBeenCalled()
  })

  it('direção fora da lista: aceita o ângulo em graus', async () => {
    vi.resetModules()
    const updateTechnicalConfiguration = vi.fn(async () => jsonResponse({}))
    installApiMock({ updateTechnicalConfiguration })

    await renderPage()
    await screen.findByText('0 de 7 itens informados')
    fireEvent.change(screen.getByLabelText('Para onde as placas estão viradas'), { target: { value: 'custom' } })
    fireEvent.change(screen.getByLabelText('Ângulo da direção (graus)'), { target: { value: '20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar instalação' }))

    await waitFor(() =>
      expect(updateTechnicalConfiguration).toHaveBeenCalledWith(singlePlant.id, { array_azimuth_degrees: '20' }),
    )
  })

  it('salva a localização convertendo a vírgula', async () => {
    vi.resetModules()
    const updatePlantLocation = vi.fn(async () => jsonResponse({}))
    installApiMock({ updatePlantLocation })

    await renderPage()
    await screen.findByText('0 de 7 itens informados')
    fireEvent.change(screen.getByLabelText('Latitude'), { target: { value: '-17,74' } })
    fireEvent.change(screen.getByLabelText('Longitude'), { target: { value: '-48,62' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar localização' }))

    await waitFor(() =>
      expect(updatePlantLocation).toHaveBeenCalledWith(singlePlant.id, { latitude: '-17.74', longitude: '-48.62' }),
    )
  })

  it('salva o investimento no formato brasileiro (11.200,00)', async () => {
    vi.resetModules()
    const updateFinancialConfiguration = vi.fn(async () => jsonResponse({}))
    installApiMock({ updateFinancialConfiguration })

    await renderPage()
    await screen.findByText('0 de 7 itens informados')
    fireEvent.change(screen.getByLabelText('Valor total investido (R$)'), { target: { value: '11.200,00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar investimento' }))

    await waitFor(() =>
      expect(updateFinancialConfiguration).toHaveBeenCalledWith(singlePlant.id, { investment_amount_brl: '11200.00' }),
    )
  })

  it('preenche os formulários com o que já foi informado', async () => {
    vi.resetModules()
    installApiMock({
      fetchPlantSetup: vi.fn(async () =>
        jsonResponse(
          setupPayload({
            technical: {
              plant_id: singlePlant.id,
              dc_capacity_kwp: '4.400',
              ac_capacity_kw: null,
              array_tilt_degrees: '15.00',
              array_azimuth_degrees: '0.00',
              module_technology: 'MONOCRYSTALLINE_SILICON',
              commissioned_on: '2025-09-01',
              devices: [],
            },
            financial: { plant_id: singlePlant.id, investment_amount_brl: '11200.00', investment_recorded_on: null },
          }),
        ),
      ),
    })

    await renderPage()

    expect(await screen.findByLabelText('Potência das placas (kWp)')).toHaveValue('4,4')
    expect(screen.getByLabelText('Mês em que a usina foi ligada')).toHaveValue('2025-09')
    expect(screen.getByLabelText('Para onde as placas estão viradas')).toHaveValue('0')
    expect(screen.getByLabelText('Valor total investido (R$)')).toHaveValue('11.200,00')
  })

  it('perfil sem permissão recebe mensagem clara', async () => {
    vi.resetModules()
    installApiMock({ updatePlantLocation: vi.fn(async () => jsonResponse({ detail: 'forbidden' }, 403)) })

    await renderPage()
    await screen.findByText('0 de 7 itens informados')
    fireEvent.change(screen.getByLabelText('Latitude'), { target: { value: '-17,74' } })
    fireEvent.change(screen.getByLabelText('Longitude'), { target: { value: '-48,62' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar localização' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('não tem permissão')
  })
})
