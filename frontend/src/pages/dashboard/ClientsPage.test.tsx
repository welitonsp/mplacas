import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { jsonResponse } from '../../test/dashboardFixtures'

vi.mock('../../env', () => ({ API_URL: 'https://api.example.test' }))

const fetchClients = vi.fn()
const createClient = vi.fn()
const reinviteClient = vi.fn()
const fetchClient = vi.fn()
const resetClientAccess = vi.fn()
const setClientActive = vi.fn()
vi.mock('../../lib/api', () => ({
  fetchClients: (...args: unknown[]) => fetchClients(...args),
  createClient: (...args: unknown[]) => createClient(...args),
  reinviteClient: (...args: unknown[]) => reinviteClient(...args),
  fetchClient: (...args: unknown[]) => fetchClient(...args),
  resetClientAccess: (...args: unknown[]) => resetClientAccess(...args),
  setClientActive: (...args: unknown[]) => setClientActive(...args),
}))

let meValue: { me: unknown; loading: boolean } = { me: null, loading: false }
vi.mock('../../contexts/MeContext', () => ({ useMe: () => meValue }))

import { ClientsPage } from './ClientsPage'

const OPERATOR = { username: 'dono@x.com', role: 'ADMIN', organizationName: 'Dono', isPlatformOperator: true }
const CLIENT = {
  organization_id: 'o1',
  name: 'Rogério',
  slug: 'rogerio',
  active: true,
  created_at: '2026-10-31T10:00:00Z',
  users: 0,
  plants: 0,
  connections: 0,
  admin_username: 'rogerio@x.com',
  invitation_pending_until: '2026-11-03T10:00:00Z',
  stage: 'CONVIDADO',
  last_success_at: null,
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ClientsPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  fetchClient.mockReset()
  resetClientAccess.mockReset()
  setClientActive.mockReset()
  fetchClients.mockReset()
  createClient.mockReset()
  reinviteClient.mockReset()
})

describe('ClientsPage (ADR-093)', () => {
  it('cliente comum não vê a área nem chama a API', () => {
    meValue = { me: { ...OPERATOR, isPlatformOperator: false }, loading: false }
    renderPage()
    expect(screen.getByText('Esta área é só para o dono da plataforma.')).toBeInTheDocument()
    expect(fetchClients).not.toHaveBeenCalled()
  })

  it('convida e mostra o link uma vez, com o token no fragmento', async () => {
    meValue = { me: OPERATOR, loading: false }
    fetchClients.mockResolvedValue(jsonResponse({ items: [] }))
    createClient.mockResolvedValue(
      jsonResponse(
        {
          organization_id: 'o1',
          name: 'Rogério',
          slug: 'rogerio',
          invitation: { username: 'rogerio@x.com', expires_at: '2026-11-03T10:00:00Z', token: 'tok-123' },
        },
        201,
      ),
    )
    renderPage()
    expect(await screen.findByText('Nenhum cliente ainda. Convide o primeiro acima.')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Nome do cliente'), { target: { value: ' Rogério ' } })
    fireEvent.change(screen.getByLabelText('E-mail do cliente (vira o usuário dele)'), {
      target: { value: 'rogerio@x.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Gerar convite' }))

    const link = (await screen.findByLabelText('Link do convite')) as HTMLInputElement
    expect(createClient).toHaveBeenCalledWith({ name: 'Rogério', admin_username: 'rogerio@x.com' })
    expect(link.value).toMatch(/\/convite#token=tok-123$/)

    fireEvent.click(screen.getByRole('button', { name: 'Já enviei, fechar' }))
    expect(screen.queryByLabelText('Link do convite')).not.toBeInTheDocument()
    expect(document.body.innerHTML).not.toContain('tok-123')
  })

  it('valida o e-mail antes de enviar', async () => {
    meValue = { me: OPERATOR, loading: false }
    fetchClients.mockResolvedValue(jsonResponse({ items: [] }))
    renderPage()
    fireEvent.change(screen.getByLabelText('Nome do cliente'), { target: { value: 'Rogério' } })
    fireEvent.change(screen.getByLabelText('E-mail do cliente (vira o usuário dele)'), { target: { value: 'sem-email' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gerar convite' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('e-mail válido')
    expect(createClient).not.toHaveBeenCalled()
  })

  it('lista clientes e gera novo convite para quem ainda não entrou', async () => {
    meValue = { me: OPERATOR, loading: false }
    fetchClients.mockResolvedValue(
      jsonResponse({ items: [CLIENT, { ...CLIENT, organization_id: 'o2', name: 'Maria', users: 1, connections: 1, stage: 'RECEBENDO_DADOS' }] }),
    )
    reinviteClient.mockResolvedValue(
      jsonResponse(
        {
          organization_id: 'o1',
          invitation: { username: 'rogerio@x.com', expires_at: '2026-11-04T10:00:00Z', token: 'tok-novo' },
        },
        201,
      ),
    )
    renderPage()
    const list = await screen.findByRole('list', { name: 'Clientes' })
    expect(within(list).getByText('Convidado')).toBeInTheDocument()
    expect(within(list).getByText('Recebendo dados')).toBeInTheDocument()
    expect(within(list).queryByRole('button', { name: 'Gerar novo convite para Maria' })).not.toBeInTheDocument()

    fireEvent.click(within(list).getByRole('button', { name: 'Gerar novo convite para Rogério' }))
    const link = (await screen.findByLabelText('Link do convite')) as HTMLInputElement
    expect(reinviteClient).toHaveBeenCalledWith('o1')
    expect(link.value).toContain('tok-novo')
  })
})


function detailPayload(overrides: Record<string, unknown> = {}) {
  return {
    organization_id: 'o1',
    name: 'Rogério',
    active: true,
    created_at: '2026-10-31T10:00:00Z',
    stage: 'ENTROU',
    admin_username: 'rogerio@x.com',
    users: [{ username: 'rogerio@x.com', role: 'ADMIN', active: true, created_at: '2026-10-31T11:00:00Z' }],
    plants: [],
    connection: null,
    pending_link: null,
    activity: [
      {
        action: 'provider_account.verify_failed',
        outcome: 'FAILED',
        at: '2026-11-02T16:53:00Z',
        details: { provider: 'GROWATT', reason: 'provider_login_blocked' },
      },
      { action: 'invitations.accept', outcome: 'SUCCEEDED', at: '2026-10-31T11:00:00Z', details: {} },
    ],
    ...overrides,
  }
}

describe('ClientsPage — ficha do cliente (ADR-095)', () => {
  it('abre a ficha com etapa e histórico traduzido', async () => {
    meValue = { me: OPERATOR, loading: false }
    fetchClients.mockResolvedValue(jsonResponse({ items: [{ ...CLIENT, users: 1, stage: 'ENTROU' }] }))
    fetchClient.mockResolvedValue(jsonResponse(detailPayload()))
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Abrir ficha de Rogério' }))

    expect(await screen.findByRole('heading', { name: 'Rogério' })).toBeInTheDocument()
    expect(fetchClient).toHaveBeenCalledWith('o1')
    const history = screen.getByRole('list', { name: 'Histórico do cliente' })
    expect(within(history).getByText(/a Growatt bloqueou o login por senha/)).toBeInTheDocument()
    expect(within(history).getByText('Cliente aceitou o convite e criou a senha')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Novo convite' })).not.toBeInTheDocument()
  })

  it('redefinir acesso mostra o link uma vez, com a frase certa', async () => {
    meValue = { me: OPERATOR, loading: false }
    fetchClients.mockResolvedValue(jsonResponse({ items: [{ ...CLIENT, users: 1, stage: 'ENTROU' }] }))
    fetchClient.mockResolvedValue(jsonResponse(detailPayload()))
    resetClientAccess.mockResolvedValue(
      jsonResponse(
        {
          organization_id: 'o1',
          invitation: { username: 'rogerio@x.com', expires_at: '2026-11-05T10:00:00Z', token: 'tok-reset' },
        },
        201,
      ),
    )
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Abrir ficha de Rogério' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Redefinir acesso' }))

    expect(await screen.findByRole('heading', { name: 'Link para Rogério redefinir o acesso' })).toBeInTheDocument()
    expect((screen.getByLabelText('Link do convite') as HTMLInputElement).value).toMatch(/#token=tok-reset$/)
    expect(resetClientAccess).toHaveBeenCalledWith('o1')
  })

  it('desativar pede confirmação', async () => {
    meValue = { me: OPERATOR, loading: false }
    fetchClients.mockResolvedValue(jsonResponse({ items: [{ ...CLIENT, users: 1, stage: 'ENTROU' }] }))
    fetchClient
      .mockResolvedValueOnce(jsonResponse(detailPayload()))
      .mockResolvedValue(jsonResponse(detailPayload({ active: false, stage: 'DESATIVADO' })))
    setClientActive.mockResolvedValue(jsonResponse({ organization_id: 'o1', active: false }))
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Abrir ficha de Rogério' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Desativar cliente' }))
    expect(setClientActive).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Sim, desativar' }))

    expect(await screen.findByRole('button', { name: 'Reativar cliente' })).toBeInTheDocument()
    expect(setClientActive).toHaveBeenCalledWith('o1', false)
    expect(screen.getByText('Desativado')).toBeInTheDocument()
  })
})
