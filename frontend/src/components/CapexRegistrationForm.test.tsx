import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { CapexRegistrationForm } from './CapexRegistrationForm'
import * as api from '../lib/api'

describe('CapexRegistrationForm', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('dispara a chamada PATCH correta em uma submissão bem-sucedida', async () => {
    const onSuccess = vi.fn()
    const updateSpy = vi
      .spyOn(api, 'updateFinancialConfiguration')
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }))

    render(<CapexRegistrationForm plantId="plant-1" onSuccess={onSuccess} />)

    fireEvent.change(screen.getByLabelText(/valor investido/i), { target: { value: '48000.00' } })
    fireEvent.change(screen.getByLabelText(/data do investimento/i), { target: { value: '2024-03-11' } })
    fireEvent.click(screen.getByRole('button', { name: /cadastrar investimento/i }))

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith('plant-1', {
        investment_amount_brl: '48000.00',
        investment_recorded_on: '2024-03-11',
      })
    )
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1))
  })

  it('envia só o valor quando a data não é preenchida', async () => {
    const onSuccess = vi.fn()
    const updateSpy = vi
      .spyOn(api, 'updateFinancialConfiguration')
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }))

    render(<CapexRegistrationForm plantId="plant-1" onSuccess={onSuccess} />)

    fireEvent.change(screen.getByLabelText(/valor investido/i), { target: { value: '48000' } })
    fireEvent.click(screen.getByRole('button', { name: /cadastrar investimento/i }))

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith('plant-1', { investment_amount_brl: '48000' })
    )
  })

  it('mostra mensagem de erro e não chama onSuccess quando o backend recusa (403)', async () => {
    const onSuccess = vi.fn()
    vi.spyOn(api, 'updateFinancialConfiguration').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'forbidden' }), { status: 403 })
    )

    render(<CapexRegistrationForm plantId="plant-1" onSuccess={onSuccess} />)

    fireEvent.change(screen.getByLabelText(/valor investido/i), { target: { value: '48000' } })
    fireEvent.click(screen.getByRole('button', { name: /cadastrar investimento/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/não tem permissão/i)
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('exibe erro de validação quando o valor não é positivo, sem chamar a API', async () => {
    const updateSpy = vi.spyOn(api, 'updateFinancialConfiguration')

    render(<CapexRegistrationForm plantId="plant-1" onSuccess={vi.fn()} />)

    fireEvent.change(screen.getByLabelText(/valor investido/i), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: /cadastrar investimento/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/maior que zero/i)
    expect(updateSpy).not.toHaveBeenCalled()
  })
})
