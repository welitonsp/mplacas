import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

const SECRET = 'senha-do-app-123'
const LOGIN = 'rogerio@example.com'
const TICKET = 'v1.bilhete-cifrado'

function preview(overrides: Record<string, unknown> = {}) {
  return {
    provider: 'NEPVIEWER',
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

function submitLogin(password = SECRET) {
  fireEvent.change(screen.getByLabelText('Usuário do app NEPViewer'), { target: { value: LOGIN } })
  fireEvent.change(screen.getByLabelText('Senha do app NEPViewer'), { target: { value: password } })
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
    submitLogin()

    expect(await screen.findByRole('heading', { name: 'Lendo sua usina' })).toBeInTheDocument()
    expect(screen.getByText(/Nada é salvo antes da sua revisão/)).toBeInTheDocument()
    expect(previewFirstPlant).toHaveBeenCalledWith({ provider: 'NEPVIEWER', login: LOGIN, password: SECRET })
    resolvePreview(jsonResponse(preview()))

    expect(await screen.findByRole('heading', { name: 'Encontramos sua usina' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Nome da usina/)).toHaveValue('Usina do Rogério')
    expect(screen.getByLabelText(/Potência dos painéis/)).toHaveValue('6.6')
    expect(screen.getAllByText('Veio da NEPViewer').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Estimado — confira').length).toBe(3)
    expect(screen.getByText(/Cidade informada pela NEPViewer: Caldas Novas/)).toBeInTheDocument()
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

  it('recusa da marca volta ao passo 1 com o usuário preenchido e o motivo', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse({ detail: 'provider_login_failed' }, 422))
    renderPanel()
    submitLogin()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('A NEPViewer recusou o usuário ou a senha')
    expect(alert).not.toHaveTextContent(SECRET)
    expect(screen.getByLabelText('Usuário do app NEPViewer')).toHaveValue(LOGIN)
    expect(confirmFirstPlant).not.toHaveBeenCalled()
  })

  it('o passo 1 oferece só a NEPViewer, como texto, sem escolha de marca nem token', () => {
    renderPanel()
    const form = screen.getByRole('form', { name: 'Conectar a usina' })
    expect(within(form).queryByRole('radio')).not.toBeInTheDocument()
    expect(within(form).queryByRole('combobox')).not.toBeInTheDocument()
    expect(within(form).getByText('Marca do inversor')).toBeInTheDocument()
    expect(within(form).getByText('NEPViewer')).toBeInTheDocument()
    expect(screen.queryByText(/Growatt|ShinePhone/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Token/)).not.toBeInTheDocument()
  })

  it.each([
    ['provider_unsupported', 'Essa marca não é mais suportada. Hoje a MPlacas conecta apenas inversores NEPViewer.'],
    ['provider_discontinued', 'A integração com essa marca foi desativada. Seu histórico continua disponível.'],
  ])('erro %s volta ao passo 1 com o texto em português', async (code, text) => {
    previewFirstPlant.mockResolvedValue(jsonResponse({ detail: code }, 422))
    renderPanel()
    submitLogin()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(text)
    expect(alert).not.toHaveTextContent(SECRET)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Ler minha usina' })).toBeVisible())
  })

  describe('leitura com falha depois do 200', () => {
    const MENSAGEM = 'Não foi possível concluir agora. Tente novamente.'

    async function esperaVoltarAoPasso1() {
      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(MENSAGEM)
      expect(alert).not.toHaveTextContent(SECRET)
      await waitFor(() => expect(screen.getByRole('button', { name: 'Ler minha usina' })).toBeVisible())
      expect(screen.queryByRole('heading', { name: 'Lendo sua usina' })).not.toBeInTheDocument()
      // A senha não aparece em nenhum texto da tela; no campo continua mascarada,
      // como em qualquer outro erro do passo 1.
      expect(document.body.textContent).not.toContain(SECRET)
      expect(screen.getByLabelText('Senha do app NEPViewer')).toHaveAttribute('type', 'password')
    }

    async function podeEnviarDeNovo() {
      previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
      fireEvent.click(screen.getByRole('button', { name: 'Ler minha usina' }))
      await screen.findByRole('heading', { name: 'Encontramos sua usina' })
      expect(previewFirstPlant).toHaveBeenCalledTimes(2)
      expect(previewFirstPlant).toHaveBeenLastCalledWith({ provider: 'NEPVIEWER', login: LOGIN, password: SECRET })
      expect(document.body.innerHTML).not.toContain(SECRET)
    }

    it('200 sem JSON volta ao passo 1 com mensagem fixa e permite tentar de novo', async () => {
      previewFirstPlant.mockResolvedValue(new Response('<html>erro do proxy</html>', { status: 200 }))
      renderPanel()
      submitLogin()
      await esperaVoltarAoPasso1()
      expect(screen.queryByText(/proxy/)).not.toBeInTheDocument()
      await podeEnviarDeNovo()
    })

    it('200 com JSON de formato errado volta ao passo 1 com mensagem fixa', async () => {
      previewFirstPlant.mockResolvedValue(jsonResponse({ inesperado: true }))
      renderPanel()
      submitLogin()
      await esperaVoltarAoPasso1()
      await podeEnviarDeNovo()
    })

    it('falha de rede volta ao passo 1 com mensagem fixa', async () => {
      previewFirstPlant.mockRejectedValue(new TypeError('Failed to fetch'))
      renderPanel()
      submitLogin()
      await esperaVoltarAoPasso1()
      await podeEnviarDeNovo()
    })
  })

  it('leitura vencida ao salvar volta para conectar de novo', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
    confirmFirstPlant.mockResolvedValue(jsonResponse({ detail: 'connect_ticket_invalid' }, 422))
    renderPanel()
    submitLogin()
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
    submitLogin()
    expect(await screen.findByText(/não informou a potência dos painéis nem a localização/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Salvar usina' })).toBeEnabled()
  })

  it('conta que já tem usina recarrega a lista', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse({ detail: 'plant_already_exists' }, 409))
    renderPanel()
    submitLogin()
    expect(await screen.findByRole('alert')).toHaveTextContent('Esta conta já tem uma usina')
    expect(reload).toHaveBeenCalled()
  })
})


describe('Assistente — revisão do quality gate', () => {
  it('campo editado troca o selo para "Informado por você"', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
    renderPanel()
    submitLogin()
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
    submitLogin()
    expect(await screen.findByRole('heading', { name: 'Conta conectada, mas sem usina' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Salvar usina' }))
    expect(await screen.findByRole('heading', { name: /salva, mas confira a conta/ })).toBeInTheDocument()
    expect(screen.queryByText(/salva!/)).not.toBeInTheDocument()
  })

  it('segundo "Salvar" com usina já criada recarrega a lista', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
    confirmFirstPlant.mockResolvedValue(jsonResponse({ detail: 'plant_already_exists' }, 409))
    renderPanel()
    submitLogin()
    fireEvent.click(await screen.findByRole('button', { name: 'Salvar usina' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Esta conta já tem uma usina')
    expect(reload).toHaveBeenCalled()
  })

  it('latitude sem longitude é recusada antes de enviar', async () => {
    previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
    renderPanel()
    submitLogin()
    fireEvent.change(await screen.findByLabelText('Longitude'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar usina' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('latitude e longitude juntas')
    expect(confirmFirstPlant).not.toHaveBeenCalled()
  })

  it('foco vai para o título da leitura e volta ao passo 1 no erro', async () => {
    let resolvePreview: (value: Response) => void = () => undefined
    previewFirstPlant.mockReturnValue(new Promise<Response>((resolve) => (resolvePreview = resolve)))
    renderPanel()
    submitLogin()
    const heading = await screen.findByRole('heading', { name: 'Lendo sua usina' })
    expect(heading).toHaveFocus()
    resolvePreview(jsonResponse({ detail: 'provider_login_failed' }, 422))
    await screen.findByRole('alert')
    await waitFor(() => expect(document.activeElement?.tagName).not.toBe('BODY'))
  })

  it('nada de senha, token ou bilhete em storage ou na URL', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    previewFirstPlant.mockResolvedValue(jsonResponse(preview()))
    renderPanel()
    submitLogin()
    await screen.findByRole('heading', { name: 'Encontramos sua usina' })
    for (const call of setItem.mock.calls) {
      expect(String(call[1])).not.toContain(SECRET)
      expect(String(call[1])).not.toContain(TICKET)
    }
    expect(window.location.href).not.toContain(TICKET)
    setItem.mockRestore()
  })
})
