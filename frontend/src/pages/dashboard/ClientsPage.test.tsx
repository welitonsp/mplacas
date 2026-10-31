import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { jsonResponse } from '../../test/dashboardFixtures'

vi.mock('../../env', () => ({ API_URL: 'https://api.example.test' }))

const fetchClients = vi.fn()
const createClient = vi.fn()
const reinviteClient = vi.fn()
vi.mock('../../lib/api', () => ({
  fetchClients: (...args: unknown[]) => fetchClients(...args),
  createClient: (...args: unknown[]) => createClient(...args),
  reinviteClient: (...args: unknown[]) => reinviteClient(...args),
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
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ClientsPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
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
      jsonResponse({ items: [CLIENT, { ...CLIENT, organization_id: 'o2', name: 'Maria', users: 1, connections: 1 }] }),
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
    expect(within(list).getByText(/Convite enviado/)).toBeInTheDocument()
    expect(within(list).getByText(/Usina conectada/)).toBeInTheDocument()
    expect(within(list).queryByRole('button', { name: 'Gerar novo convite para Maria' })).not.toBeInTheDocument()

    fireEvent.click(within(list).getByRole('button', { name: 'Gerar novo convite para Rogério' }))
    const link = (await screen.findByLabelText('Link do convite')) as HTMLInputElement
    expect(reinviteClient).toHaveBeenCalledWith('o1')
    expect(link.value).toContain('tok-novo')
  })
})
