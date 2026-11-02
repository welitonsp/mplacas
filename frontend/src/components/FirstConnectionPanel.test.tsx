import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { jsonResponse } from '../test/dashboardFixtures'

vi.mock('../env', () => ({ API_URL: 'https://api.example.test' }))

const previewFirstPlant = vi.fn()
const confirmFirstPlant = vi.fn()
vi.mock('../lib/api', () => ({
  previewFirstPlant: (...args: unknown[]) => previewFirstPlant(...args),
  confirmFirstPlant: (...args: unknown[]) => confirmFirstPlant(...args),
}))

const reload = vi.fn()
vi.mock('../contexts/PlantContext', () => ({ usePlant: () => ({ reload }) }))

import { FirstConnectionPanel } from './FirstConnectionPanel'

const SECRET = 'token-do-app-123'
const TICKET = 'v1.bilhete-cifrado'

function preview(overrides: Record<string, unknown> = {}) {
  return {
    provider: 'GROWATT_TOKEN',
    devices_found: 1,
    plant: {
      name: 'Usina do Rogério',
      installed_power_kwp: '6.6',
      latitude: '-17.74',
      longitude: '-48.62',
      city: 'Caldas Novas',
      array_tilt_degrees: '18',
      array_azimuth_degrees: '0',
      module_technology: 'MONOCRYSTALLINE_SILICON',
    },
    origins: {
      name: 'BRAND',
      dc_capacity_kwp: 'BRAND',
      location: 'BRAND',
      array_tilt_degrees: 'ESTIMATE',
      array_azimuth_degrees: 'ESTIMATE',
      module_technology: 'ESTIMATE',
    },
    ticket: TICKET,
    expires_at: '2026-11-02T18:30:00Z',
    ...overrides,
  }
}

function renderPanel() {
  return render(
    <MemoryRouter initialEntries={['/dashboard/inicio']}>
      <Routes>
        <Route path="/dashboard/inicio" element={<FirstConnectionPanel />} />
        <Route path="/dashboard/minha-usina" element={<p>minha usina</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

function submitToken(token = SECRET) {
  fireEvent.click(screen.getByLabelText('Growatt — token (recomendado)'))
  fireEvent.change(screen.getByLabelText('Token da API (app ShinePhone)'), { target: { value: token } })
  fireEvent.click(screen.getByRole('button', { name: 'Ler minha usina' }))
}

beforeEach(() => {
  previewFirstPlant.mockReset()
  confirmFirstPlant.mockReset()
  reload.mockReset()
})

describe('Assistente de primeiro acesso (ADR-096)', () => {
  it('conecta, mostra a leitura, revisa com a origem de cada campo e salva', async () => {
    let resolvePreview: (value: Response) => void = () => undefined
    previewFirstPlant.mockReturnValue(new Promise<Response>((resolve) => (resolvePreview = resolve)))
    confirmFirstPlant.mockResolvedValue(
      jsonResponse(
        {
          plant_id: 'p1',
          plant_name: 'Sítio do Rogério',
          connection: { status: 'CONECTADA', devices_found: 1 },
          auto_filled: { dc_capacity_kwp: 'BRAND' },
        },
        201,
      ),
    )
    renderPanel()
    expect(screen.getByRole('list', { name: /Etapas do cadastro: passo 1 de 3/ })).toBeInTheDocument()
    submitToken()

    expect(await screen.findByRole('heading', { name: 'Lendo sua usina' })).toBeInTheDocument()
    expect(screen.getByText(/Nada é salvo antes da sua revisão/)).toBeInTheDocument()
    expect(previewFirstPlant).toHaveBeenCalledWith({ provider: 'GROWATT_TOKEN', login: '', password: SECRET })
    resolvePreview(jsonResponse(preview()))

    expect(await screen.findByRole('heading', { name: 'Encontramos sua usina' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Nome da usina/)).toHaveValue('Usina do Rogério')
    expect(screen.getByLabelText(/Potência dos painéis/)).toHaveValue('6.6')
    expect(screen.getAllByText('Veio da Growatt').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Estimado — confira').length).toBe(3)
    expect(screen.getByText(/Cidade informada pela Growatt: Caldas Novas/)).toBeInTheDocument()
    expect(document.body.innerHTML).not.toContain(SECRET)

    fireEvent.change(screen.getByLabelText(/Nome da usina/), { target: { value: 'Sítio do Rogério' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar usina' }))

    expect(await screen.findByRole('heading', { name: /Sítio do Rogério.*salva/ })).toBeInTheDocument()
    expect(confirmFirstPlant).toHaveBeenCalledWith(TICKET, {
      name: 'Sítio do Rogério',
      installed_power_kwp: '6.6',
      latitude: '-17.74',
      longitude: '-48.62',
      array_tilt_degrees: '18',
      array_azimuth_degrees: '0',
      module_technology: 'MONOCRYSTALLINE_SILICON',
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ir para o painel' }))
    expect(reload).toHaveBeenCalled()
  })

  it('recusa da marca volta ao passo 1 com a marca escolhida e o motivo', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse({ detail: 'provider_token_failed' }, 422))
    renderPanel()
    submitToken()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('A Growatt recusou o token')
    expect(alert).not.toHaveTextContent(SECRET)
    expect(screen.getByLabelText('Growatt — token (recomendado)')).toBeChecked()
    expect(confirmFirstPlant).not.toHaveBeenCalled()
  })

  it('leitura vencida ao salvar volta para conectar de novo', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
    confirmFirstPlant.mockResolvedValue(jsonResponse({ detail: 'connect_ticket_invalid' }, 422))
    renderPanel()
    submitToken()
    fireEvent.click(await screen.findByRole('button', { name: 'Salvar usina' }))

    expect(await screen.findByText(/A leitura da usina expirou/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Ler minha usina' })).toBeVisible())
  })

  it('avisa quando a marca não informa potência nem localização, sem impedir salvar', async () => {
    previewFirstPlant.mockResolvedValue(
      jsonResponse(
        preview({
          plant: {
            name: 'Minha usina',
            installed_power_kwp: null,
            latitude: null,
            longitude: null,
            city: null,
            array_tilt_degrees: null,
            array_azimuth_degrees: null,
            module_technology: null,
          },
          origins: {},
        }),
      ),
    )
    renderPanel()
    submitToken()
    expect(await screen.findByText(/não informou a potência dos painéis nem a localização/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Salvar usina' })).toBeEnabled()
  })

  it('conta que já tem usina recarrega a lista', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse({ detail: 'plant_already_exists' }, 409))
    renderPanel()
    submitToken()
    expect(await screen.findByRole('alert')).toHaveTextContent('Esta conta já tem uma usina')
    expect(reload).toHaveBeenCalled()
  })
})


describe('Assistente — revisão do quality gate', () => {
  it('campo editado troca o selo para "Informado por você"', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
    renderPanel()
    submitToken()
    const power = await screen.findByLabelText(/Potência dos painéis/)
    fireEvent.change(power, { target: { value: '7.2' } })
    expect(screen.getByText('Informado por você')).toBeInTheDocument()
    expect(screen.getByLabelText('Latitude')).toHaveValue('-17.74')
    expect(screen.getByRole('group', { name: /Localização/ })).toBeInTheDocument()
  })

  it('conta sem aparelhos não termina em sucesso', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse(preview({ devices_found: 0 })))
    confirmFirstPlant.mockResolvedValue(
      jsonResponse(
        { plant_id: 'p1', plant_name: 'Casa', connection: { devices_found: 0 }, auto_filled: {} },
        201,
      ),
    )
    renderPanel()
    submitToken()
    expect(await screen.findByRole('heading', { name: 'Conta conectada, mas sem usina' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Salvar usina' }))
    expect(await screen.findByRole('heading', { name: /salva, mas confira a conta/ })).toBeInTheDocument()
    expect(screen.queryByText(/salva!/)).not.toBeInTheDocument()
  })

  it('segundo "Salvar" com usina já criada recarrega a lista', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
    confirmFirstPlant.mockResolvedValue(jsonResponse({ detail: 'plant_already_exists' }, 409))
    renderPanel()
    submitToken()
    fireEvent.click(await screen.findByRole('button', { name: 'Salvar usina' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Esta conta já tem uma usina')
    expect(reload).toHaveBeenCalled()
  })

  it('latitude sem longitude é recusada antes de enviar', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
    renderPanel()
    submitToken()
    fireEvent.change(await screen.findByLabelText('Longitude'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar usina' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('latitude e longitude juntas')
    expect(confirmFirstPlant).not.toHaveBeenCalled()
  })

  it('foco vai para o título da leitura e volta ao passo 1 no erro', async () => {
    let resolvePreview: (value: Response) => void = () => undefined
    previewFirstPlant.mockReturnValue(new Promise<Response>((resolve) => (resolvePreview = resolve)))
    renderPanel()
    submitToken()
    const heading = await screen.findByRole('heading', { name: 'Lendo sua usina' })
    expect(heading).toHaveFocus()
    resolvePreview(jsonResponse({ detail: 'provider_token_failed' }, 422))
    await screen.findByRole('alert')
    await waitFor(() => expect(document.activeElement?.tagName).not.toBe('BODY'))
  })

  it('nada de senha, token ou bilhete em storage ou na URL', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
    renderPanel()
    submitToken()
    await screen.findByRole('heading', { name: 'Encontramos sua usina' })
    for (const call of setItem.mock.calls) {
      expect(String(call[1])).not.toContain(SECRET)
      expect(String(call[1])).not.toContain(TICKET)
    }
    expect(window.location.href).not.toContain(TICKET)
    setItem.mockRestore()
  })
})
