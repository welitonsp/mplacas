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
  fetchProviderAccount?: ReturnType<typeof vi.fn>
  saveProviderAccount?: ReturnType<typeof vi.fn>
  deleteProviderAccount?: ReturnType<typeof vi.fn>
}

const NO_CONNECTION = {
  status: 'SEM_CONEXAO',
  provider: null,
  login_hint: null,
  connected_at: null,
  last_success_at: null,
  last_failure_at: null,
  devices_found: null,
}

const CONNECTED = {
  status: 'CONECTADA',
  provider: 'NEPVIEWER',
  login_hint: 'cl***@example.com',
  connected_at: '2026-10-29T18:44:00Z',
  last_success_at: '2026-10-30T09:07:00Z',
  last_failure_at: null,
  devices_found: null,
}

function installApiMock(mocks: Mocks = {}) {
  const resolved = {
    fetchPlantSetup: mocks.fetchPlantSetup ?? vi.fn(async () => jsonResponse(setupPayload())),
    updateTechnicalConfiguration: mocks.updateTechnicalConfiguration ?? vi.fn(async () => jsonResponse({})),
    updatePlantLocation: mocks.updatePlantLocation ?? vi.fn(async () => jsonResponse({})),
    updateFinancialConfiguration: mocks.updateFinancialConfiguration ?? vi.fn(async () => jsonResponse({})),
    fetchProviderAccount: mocks.fetchProviderAccount ?? vi.fn(async () => jsonResponse(NO_CONNECTION)),
    saveProviderAccount: mocks.saveProviderAccount ?? vi.fn(async () => jsonResponse(CONNECTED)),
    deleteProviderAccount: mocks.deleteProviderAccount ?? vi.fn(async () => new Response(null, { status: 204 })),
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

describe('PlantSetupPage — conexão com o inversor (ADR-091)', () => {
  const SECRET = 's3nh4-do-inversor'

  it('sem conexão, confere a conta, mostra quantos inversores achou e esquece a senha', async () => {
    vi.resetModules()
    const fetchProviderAccount = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(NO_CONNECTION))
      .mockResolvedValue(jsonResponse(CONNECTED))
    const saveProviderAccount = vi.fn(async () => jsonResponse({ ...CONNECTED, devices_found: 2 }))
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    installApiMock({ fetchProviderAccount, saveProviderAccount })

    await renderPage()

    expect(await screen.findByText('Nenhuma conta conectada')).toBeInTheDocument()
    const password = screen.getByLabelText('Senha do app NEPViewer')
    expect(password).toHaveAttribute('type', 'password')
    expect(password).toHaveAttribute('autocomplete', 'new-password')
    expect(password).toHaveValue('')
    fireEvent.change(screen.getByLabelText('Usuário do app NEPViewer'), { target: { value: ' cliente@example.com ' } })
    fireEvent.change(password, { target: { value: SECRET } })
    fireEvent.click(screen.getByRole('button', { name: 'Conferir e conectar' }))

    await waitFor(() =>
      expect(saveProviderAccount).toHaveBeenCalledWith(singlePlant.id, {
        provider: 'NEPVIEWER',
        login: 'cliente@example.com',
        password: SECRET,
      }),
    )
    expect(await screen.findByText('Conta conectada. 2 inversores encontrados.')).toBeInTheDocument()
    expect(await screen.findByText(/NEPViewer, conta cl\*\*\*@example.com/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Senha do app NEPViewer')).not.toBeInTheDocument()
    expect(document.body.innerHTML).not.toContain(SECRET)
    for (const call of setItem.mock.calls) expect(String(call[1])).not.toContain(SECRET)
    setItem.mockRestore()
  })

  it('mostra o motivo da recusa sem repetir o que foi digitado', async () => {
    vi.resetModules()
    const saveProviderAccount = vi.fn(async () => jsonResponse({ detail: 'provider_login_failed' }, 422))
    installApiMock({ saveProviderAccount })

    await renderPage()
    await screen.findByText('Nenhuma conta conectada')
    fireEvent.change(screen.getByLabelText('Usuário do app NEPViewer'), { target: { value: 'cliente@example.com' } })
    fireEvent.change(screen.getByLabelText('Senha do app NEPViewer'), { target: { value: SECRET } })
    fireEvent.click(screen.getByRole('button', { name: 'Conferir e conectar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A NEPViewer recusou o usuário ou a senha')
    expect(screen.getByRole('alert')).not.toHaveTextContent(SECRET)
  })

  it('não envia sem login ou senha', async () => {
    vi.resetModules()
    const saveProviderAccount = vi.fn()
    installApiMock({ saveProviderAccount })

    await renderPage()
    await screen.findByText('Nenhuma conta conectada')
    fireEvent.click(screen.getByRole('button', { name: 'Conferir e conectar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Informe o usuário do app NEPViewer.')
    expect(saveProviderAccount).not.toHaveBeenCalled()
  })

  it.each([
    [409, 'provider_account_in_use', 'Esta conta da NEPViewer já está conectada a outra usina.'],
    [429, 'provider_verify_rate_limited', 'Muitas tentativas seguidas.'],
    [503, 'provider_unavailable', 'A NEPViewer não respondeu agora.'],
    [403, 'Forbidden', 'Só o administrador da conta pode alterar a conexão.'],
  ])('traduz o erro %s (%s)', async (status, detail, message) => {
    vi.resetModules()
    installApiMock({ saveProviderAccount: vi.fn(async () => jsonResponse({ detail }, status)) })

    await renderPage()
    await screen.findByText('Nenhuma conta conectada')
    fireEvent.change(screen.getByLabelText('Usuário do app NEPViewer'), { target: { value: 'a@b.c' } })
    fireEvent.change(screen.getByLabelText('Senha do app NEPViewer'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Conferir e conectar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
  })

  it('conectada, mostra a última leitura e desconecta só depois de confirmar', async () => {
    vi.resetModules()
    const fetchProviderAccount = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(CONNECTED))
      .mockResolvedValue(jsonResponse(NO_CONNECTION))
    const deleteProviderAccount = vi.fn(async () => new Response(null, { status: 204 }))
    installApiMock({ fetchProviderAccount, deleteProviderAccount })

    await renderPage()

    expect(await screen.findByText(/Última leitura em/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Senha do app NEPViewer')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Desconectar' }))
    expect(deleteProviderAccount).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Sim, desconectar' }))

    await waitFor(() => expect(deleteProviderAccount).toHaveBeenCalledWith(singlePlant.id))
    expect(await screen.findByText('Conta desconectada. A produção deixa de ser buscada.')).toBeInTheDocument()
    expect(await screen.findByText('Nenhuma conta conectada')).toBeInTheDocument()
  })

  it('com falha na última leitura, pede a senha nova', async () => {
    vi.resetModules()
    installApiMock({
      fetchProviderAccount: vi.fn(async () =>
        jsonResponse({ ...CONNECTED, status: 'FALHA', last_failure_at: '2026-10-31T09:07:00Z' }),
      ),
    })

    await renderPage()

    expect(await screen.findByText('Conectada, mas a última leitura falhou')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Trocar senha ou conta' }))
    expect(screen.getByLabelText('Senha do app NEPViewer')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Conferir e trocar' })).toBeInTheDocument()
  })

  it('mostrar senha alterna o tipo do campo com nome claro', async () => {
    vi.resetModules()
    installApiMock()

    await renderPage()
    await screen.findByText('Nenhuma conta conectada')
    const password = screen.getByLabelText('Senha do app NEPViewer')
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar senha' }))
    expect(password).toHaveAttribute('type', 'text')
    fireEvent.click(screen.getByRole('button', { name: 'Ocultar senha' }))
    expect(password).toHaveAttribute('type', 'password')
  })

  it('ao trocar, o foco vai para o login; cancelar descarta a senha e devolve o foco', async () => {
    vi.resetModules()
    installApiMock({ fetchProviderAccount: vi.fn(async () => jsonResponse(CONNECTED)) })

    await renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Trocar senha ou conta' }))
    expect(screen.getByLabelText('Usuário do app NEPViewer')).toHaveFocus()
    fireEvent.change(screen.getByLabelText('Senha do app NEPViewer'), { target: { value: SECRET } })
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar troca' }))

    expect(screen.queryByLabelText('Senha do app NEPViewer')).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Conectada').closest('[tabindex="-1"]')).toHaveFocus())
    fireEvent.click(screen.getByRole('button', { name: 'Trocar senha ou conta' }))
    expect(screen.getByLabelText('Senha do app NEPViewer')).toHaveValue('')
  })

  it('desconectar leva o foco à confirmação; falha mantém a confirmação aberta', async () => {
    vi.resetModules()
    const deleteProviderAccount = vi.fn(async () => new Response('erro', { status: 500 }))
    installApiMock({ fetchProviderAccount: vi.fn(async () => jsonResponse(CONNECTED)), deleteProviderAccount })

    await renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Desconectar' }))
    const confirm = screen.getByRole('button', { name: 'Sim, desconectar' })
    expect(confirm).toHaveFocus()
    fireEvent.click(confirm)

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível concluir agora.')
    expect(screen.getByRole('button', { name: 'Sim, desconectar' })).toBeInTheDocument()
  })

  it('conta já removida em outra aba: avisa sem dizer que a usina sumiu e relê', async () => {
    vi.resetModules()
    const fetchProviderAccount = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(CONNECTED))
      .mockResolvedValue(jsonResponse(NO_CONNECTION))
    const deleteProviderAccount = vi.fn(async () =>
      jsonResponse({ detail: 'provider_account_not_found' }, 404),
    )
    installApiMock({ fetchProviderAccount, deleteProviderAccount })

    await renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Desconectar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sim, desconectar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Esta usina já estava sem conta conectada.')
    expect(await screen.findByText('Nenhuma conta conectada')).toBeInTheDocument()
    expect(fetchProviderAccount).toHaveBeenCalledTimes(2)
  })

  it('erro ao buscar a conexão oferece nova tentativa', async () => {
    vi.resetModules()
    const fetchProviderAccount = vi
      .fn()
      .mockResolvedValueOnce(new Response('falha', { status: 500 }))
      .mockResolvedValue(jsonResponse(NO_CONNECTION))
    installApiMock({ fetchProviderAccount })

    await renderPage()

    expect(await screen.findByText('Erro ao buscar a conexão com o inversor.')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: /Tentar novamente/ })[0])
    expect(await screen.findByText('Nenhuma conta conectada')).toBeInTheDocument()
  })

  it('o aviso de conta salva continua visível se a releitura falhar', async () => {
    vi.resetModules()
    const fetchProviderAccount = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(NO_CONNECTION))
      .mockResolvedValue(new Response('falha', { status: 500 }))
    installApiMock({
      fetchProviderAccount,
      saveProviderAccount: vi.fn(async () => jsonResponse({ ...CONNECTED, devices_found: 1 })),
    })

    await renderPage()
    await screen.findByText('Nenhuma conta conectada')
    fireEvent.change(screen.getByLabelText('Usuário do app NEPViewer'), { target: { value: 'a@b.c' } })
    fireEvent.change(screen.getByLabelText('Senha do app NEPViewer'), { target: { value: SECRET } })
    fireEvent.click(screen.getByRole('button', { name: 'Conferir e conectar' }))

    expect(await screen.findByText('Erro ao buscar a conexão com o inversor.')).toBeInTheDocument()
    expect(screen.getByText('Conta conectada. 1 inversor encontrado.')).toBeInTheDocument()
  })

  it('escolhe a Growatt e conecta com usuário e senha do app, sem token', async () => {
    vi.resetModules()
    const fetchProviderAccount = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(NO_CONNECTION))
      .mockResolvedValue(jsonResponse({ ...CONNECTED, provider: 'GROWATT', login_hint: 'ro***io' }))
    const saveProviderAccount = vi.fn(async () =>
      jsonResponse({ ...CONNECTED, provider: 'GROWATT', login_hint: 'ro***io', devices_found: 1 }),
    )
    installApiMock({ fetchProviderAccount, saveProviderAccount })

    await renderPage()
    await screen.findByText('Nenhuma conta conectada')
    const group = screen.getByRole('group', { name: 'Marca do inversor' })
    expect(within(group).getByRole('radio', { name: 'NEPViewer' })).toBeChecked()
    fireEvent.click(within(group).getByRole('radio', { name: 'Growatt' }))
    expect(screen.getByLabelText('Usuário do app Growatt')).toHaveAttribute(
      'placeholder',
      'O mesmo do app ShinePhone (Growatt)',
    )
    fireEvent.change(screen.getByLabelText('Usuário do app Growatt'), { target: { value: 'rogerio' } })
    fireEvent.change(screen.getByLabelText('Senha do app Growatt'), { target: { value: SECRET } })
    fireEvent.click(screen.getByRole('button', { name: 'Conferir e conectar' }))

    await waitFor(() =>
      expect(saveProviderAccount).toHaveBeenCalledWith(singlePlant.id, {
        provider: 'GROWATT',
        login: 'rogerio',
        password: SECRET,
      }),
    )
    expect(await screen.findByText('Conta conectada. 1 usina encontrada na Growatt.')).toBeInTheDocument()
    expect(await screen.findByText(/Growatt, conta ro\*\*\*io/)).toBeInTheDocument()
  })

  it('bloqueio da Growatt pede para esperar, com o nome da marca', async () => {
    vi.resetModules()
    installApiMock({
      saveProviderAccount: vi.fn(async () => jsonResponse({ detail: 'provider_rate_limited' }, 503)),
    })

    await renderPage()
    await screen.findByText('Nenhuma conta conectada')
    fireEvent.click(screen.getByRole('radio', { name: 'Growatt' }))
    fireEvent.change(screen.getByLabelText('Usuário do app Growatt'), { target: { value: 'rogerio' } })
    fireEvent.change(screen.getByLabelText('Senha do app Growatt'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Conferir e conectar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A Growatt bloqueou novas tentativas por um tempo.')
  })

  it('ao trocar uma conexão Growatt, a marca já vem marcada', async () => {
    vi.resetModules()
    installApiMock({
      fetchProviderAccount: vi.fn(async () => jsonResponse({ ...CONNECTED, provider: 'GROWATT' })),
    })

    await renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Trocar senha ou conta' }))

    expect(screen.getByRole('radio', { name: 'Growatt' })).toBeChecked()
    expect(screen.getByLabelText('Senha do app Growatt')).toHaveValue('')
  })
})

