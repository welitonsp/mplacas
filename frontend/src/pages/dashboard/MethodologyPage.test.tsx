import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { MethodologyPage } from './MethodologyPage'
import { DASHBOARD_FINANCIAL_PATH, DASHBOARD_METHODOLOGY_PATH } from '../../routes'

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[DASHBOARD_METHODOLOGY_PATH]}>
      <MethodologyPage />
    </MemoryRouter>,
  )
}

describe('MethodologyPage — Como calculamos (ADR-086)', () => {
  it('título único h1, volta para Dinheiro e uma seção por pergunta', () => {
    renderPage()

    expect(screen.getByRole('heading', { level: 1, name: 'Como calculamos' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Voltar para Dinheiro/ })).toHaveAttribute('href', DASHBOARD_FINANCIAL_PATH)
    for (const name of ['De onde vem cada número', 'Placas × distribuidora', 'Conferência da distribuidora', 'Economia do ciclo', 'Limites']) {
      expect(screen.getByRole('heading', { level: 2, name })).toBeInTheDocument()
    }
  })

  it('cita as normas e as fórmulas que o motor usa, sem números de usina', () => {
    renderPage()

    expect(screen.getByText(/REH 3\.407\/2024 e REH 3\.544\/2025/)).toBeInTheDocument()
    expect(screen.getAllByText(/Lei 14\.300\/2022/).length).toBeGreaterThan(1)
    expect(screen.getByText(/REN 1\.000\/2021/)).toBeInTheDocument()
    expect(screen.getByText('registrado pelo medidor + saldo anterior = créditos usados + saldo novo')).toBeInTheDocument()
    expect(screen.getByText('valor de 1 kWh = tarifa cheia com impostos + bandeira − Fio B')).toBeInTheDocument()
    expect(screen.getByText('economia = conta sem a usina − valor pago na fatura')).toBeInTheDocument()
    expect(screen.queryByText(/kWh \d/)).not.toBeInTheDocument()
  })
})
