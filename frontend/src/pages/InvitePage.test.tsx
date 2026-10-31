import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { jsonResponse } from '../test/dashboardFixtures'

vi.mock('../env', () => ({ API_URL: 'https://api.example.test' }))

const inspectInvitation = vi.fn()
const acceptInvitation = vi.fn()
vi.mock('../lib/api', () => ({
  inspectInvitation: (...args: unknown[]) => inspectInvitation(...args),
  acceptInvitation: (...args: unknown[]) => acceptInvitation(...args),
  warmUpApi: vi.fn(),
}))

const adoptSession = vi.fn()
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ adoptSession }),
}))

import { InvitePage } from './InvitePage'

const TOKEN = 'convite-secreto-123'
const SENHA = 'uma frase longa'
const PREVIEW = {
  organization_name: 'Usina do Rogério',
  username: 'rogerio@example.com',
  role: 'ADMIN',
  expires_at: '2026-11-03T13:00:00Z',
}

function renderAt(hash: string) {
  window.history.replaceState(null, '', `/convite${hash}`)
  return render(
    <MemoryRouter initialEntries={['/convite']}>
      <Routes>
        <Route path="/convite" element={<InvitePage />} />
        <Route path="/dashboard" element={<p>painel</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  inspectInvitation.mockReset()
  acceptInvitation.mockReset()
  adoptSession.mockReset()
})

afterEach(() => {
  window.history.replaceState(null, '', '/')
})

describe('InvitePage (ADR-093)', () => {
  it('mostra o convite e tira o token da barra de endereço', async () => {
    inspectInvitation.mockResolvedValue(jsonResponse(PREVIEW))
    renderAt(`#token=${TOKEN}`)

    expect(await screen.findByText('Usina do Rogério')).toBeInTheDocument()
    expect(screen.getByText('rogerio@example.com')).toBeInTheDocument()
    expect(inspectInvitation).toHaveBeenCalledWith(TOKEN)
    expect(window.location.hash).toBe('')
    expect(document.body.innerHTML).not.toContain(TOKEN)
  })

  it('confere senha curta e diferente antes de enviar', async () => {
    inspectInvitation.mockResolvedValue(jsonResponse(PREVIEW))
    renderAt(`#token=${TOKEN}`)
    await screen.findByText('Usina do Rogério')

    fireEvent.change(screen.getByLabelText('Nova senha'), { target: { value: 'curta' } })
    fireEvent.change(screen.getByLabelText('Repita a senha'), { target: { value: 'curta' } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar senha e entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('pelo menos 12 caracteres')

    fireEvent.change(screen.getByLabelText('Nova senha'), { target: { value: SENHA } })
    fireEvent.change(screen.getByLabelText('Repita a senha'), { target: { value: `${SENHA}!` } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar senha e entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('não são iguais')
    expect(acceptInvitation).not.toHaveBeenCalled()
  })

  it('cria a senha, entra e vai para o painel', async () => {
    inspectInvitation.mockResolvedValue(jsonResponse(PREVIEW))
    acceptInvitation.mockResolvedValue(jsonResponse({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' }))
    renderAt(`#token=${TOKEN}`)
    await screen.findByText('Usina do Rogério')

    fireEvent.change(screen.getByLabelText('Nova senha'), { target: { value: SENHA } })
    fireEvent.change(screen.getByLabelText('Repita a senha'), { target: { value: SENHA } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar senha e entrar' }))

    expect(await screen.findByText('painel')).toBeInTheDocument()
    expect(acceptInvitation).toHaveBeenCalledWith(TOKEN, SENHA)
    expect(adoptSession).toHaveBeenCalledWith('a', 'r', 'rogerio@example.com')
  })

  it('falha do servidor no aceite mantém o formulário e o convite', async () => {
    inspectInvitation.mockResolvedValue(jsonResponse(PREVIEW))
    acceptInvitation.mockResolvedValueOnce(jsonResponse({ detail: 'erro' }, 503))
    renderAt(`#token=${TOKEN}`)
    await screen.findByText('Usina do Rogério')
    fireEvent.change(screen.getByLabelText('Nova senha'), { target: { value: SENHA } })
    fireEvent.change(screen.getByLabelText('Repita a senha'), { target: { value: SENHA } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar senha e entrar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('continua valendo')
    expect(screen.getByRole('button', { name: 'Criar senha e entrar' })).toBeInTheDocument()
    expect(adoptSession).not.toHaveBeenCalled()
  })

  it('senha acima do máximo não é enviada', async () => {
    inspectInvitation.mockResolvedValue(jsonResponse(PREVIEW))
    renderAt(`#token=${TOKEN}`)
    await screen.findByText('Usina do Rogério')
    const longa = 'a'.repeat(201)
    fireEvent.change(screen.getByLabelText('Nova senha'), { target: { value: longa } })
    fireEvent.change(screen.getByLabelText('Repita a senha'), { target: { value: longa } })
    fireEvent.click(screen.getByRole('button', { name: 'Criar senha e entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('no máximo 200')
    expect(acceptInvitation).not.toHaveBeenCalled()
  })

  it('convite vencido ou usado vira aviso claro', async () => {
    inspectInvitation.mockResolvedValue(jsonResponse({ detail: 'invalid or expired invitation' }, 400))
    renderAt(`#token=${TOKEN}`)
    expect(await screen.findByRole('alert')).toHaveTextContent('Peça um novo')
  })

  it('link sem token não chama o servidor', async () => {
    renderAt('')
    expect(await screen.findByRole('alert')).toHaveTextContent('incompleto')
    await waitFor(() => expect(inspectInvitation).not.toHaveBeenCalled())
  })
})
