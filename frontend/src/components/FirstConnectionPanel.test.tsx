import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { jsonResponse } from '../test/dashboardFixtures'

vi.mock('../env', () => ({ API_URL: 'https://api.example.test' }))

const connectFirstPlant = vi.fn()
vi.mock('../lib/api', () => ({
  connectFirstPlant: (...args: unknown[]) => connectFirstPlant(...args),
}))

const reload = vi.fn()
vi.mock('../contexts/PlantContext', () => ({ usePlant: () => ({ reload }) }))

import { FirstConnectionPanel } from './FirstConnectionPanel'

const SECRET = 'senha-do-app-123'

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

function fill(brand: 'Growatt' | 'NEPViewer') {
  fireEvent.click(screen.getByLabelText(brand))
  fireEvent.change(screen.getByLabelText(`Usuário do app ${brand}`), { target: { value: 'rogerio' } })
  fireEvent.change(screen.getByLabelText(`Senha do app ${brand}`), { target: { value: SECRET } })
  fireEvent.click(screen.getByRole('button', { name: 'Conferir e criar minha usina' }))
}

beforeEach(() => {
  connectFirstPlant.mockReset()
  reload.mockReset()
})

describe('FirstConnectionPanel (ADR-093 § 7)', () => {
  it('cria a usina e separa o que veio da marca do que foi estimado', async () => {
    connectFirstPlant.mockResolvedValue(
      jsonResponse(
        {
          plant_id: 'p1',
          plant_name: 'Usina do Rogério',
          connection: { status: 'CONECTADA', devices_found: 1 },
          auto_filled: {
            name: 'BRAND',
            dc_capacity_kwp: 'BRAND',
            location: 'BRAND',
            array_tilt_degrees: 'ESTIMATE',
            module_technology: 'ESTIMATE',
          },
        },
        201,
      ),
    )
    renderPanel()
    fill('Growatt')

    expect(await screen.findByRole('heading', { name: /Usina do Rogério/ })).toBeInTheDocument()
    expect(connectFirstPlant).toHaveBeenCalledWith({ provider: 'GROWATT', login: 'rogerio', password: SECRET })
    expect(screen.getByText('Veio do aplicativo da marca')).toBeInTheDocument()
    expect(screen.getByText('Potência dos painéis')).toBeInTheDocument()
    expect(screen.getByText(/Estimado pelo sistema/)).toBeInTheDocument()
    expect(screen.getByText('Inclinação dos painéis')).toBeInTheDocument()
    expect(document.body.innerHTML).not.toContain(SECRET)

    fireEvent.click(screen.getByRole('button', { name: 'Ver minha usina' }))
    expect(reload).toHaveBeenCalled()
    expect(await screen.findByText('minha usina')).toBeInTheDocument()
  })

  it('mostra a recusa da marca sem repetir o que foi digitado', async () => {
    connectFirstPlant.mockResolvedValue(jsonResponse({ detail: 'provider_login_failed' }, 422))
    renderPanel()
    fill('NEPViewer')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('A NEPViewer recusou o usuário ou a senha')
    expect(alert).not.toHaveTextContent(SECRET)
  })

  it('conta que já tem usina recarrega a lista (sem atualizar a página)', async () => {
    connectFirstPlant.mockResolvedValue(jsonResponse({ detail: 'plant_already_exists' }, 409))
    renderPanel()
    fill('Growatt')
    expect(await screen.findByRole('alert')).toHaveTextContent('Esta conta já tem uma usina')
    expect(reload).toHaveBeenCalled()
  })

  it('conta sem aparelhos: usina criada, mas com aviso — não "Pronto!"', async () => {
    connectFirstPlant.mockResolvedValue(
      jsonResponse(
        { plant_id: 'p1', plant_name: 'Casa', connection: { devices_found: 0 }, auto_filled: {} },
        201,
      ),
    )
    renderPanel()
    fill('NEPViewer')
    expect(await screen.findByRole('heading', { name: /foi criada, mas confira a conta/ })).toBeInTheDocument()
    expect(screen.queryByText(/Pronto!/)).not.toBeInTheDocument()
  })
})
