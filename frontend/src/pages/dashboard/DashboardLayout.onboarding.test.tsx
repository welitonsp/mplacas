import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'

vi.mock('../../env', () => ({ API_URL: 'https://api.example.test' }))
vi.mock('../../lib/api', () => ({ connectFirstPlant: vi.fn() }))
vi.mock('../../components/AppShell', () => ({
  AppShell: ({ children, subnav }: { children: React.ReactNode; subnav: React.ReactNode }) => (
    <div>
      {subnav}
      {children}
    </div>
  ),
}))

let plantValue: Record<string, unknown> = {}
vi.mock('../../contexts/PlantContext', () => ({ usePlant: () => plantValue }))
let meValue: { me: unknown; loading: boolean } = { me: null, loading: false }
vi.mock('../../contexts/MeContext', () => ({ useMe: () => meValue }))

import { DashboardLayout } from './DashboardLayout'

const ADMIN = { username: 'c@x.com', role: 'ADMIN', organizationName: 'Cli', isPlatformOperator: false }

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/dashboard" element={<DashboardLayout />}>
          <Route path="inicio" element={<p>módulo início</p>} />
          <Route path="clientes" element={<p>módulo clientes</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('DashboardLayout — conta sem usina (ADR-093 § 7)', () => {
  it('admin sem usina vê a primeira conexão no lugar do módulo', async () => {
    plantValue = { plants: [], loading: false, error: null, reload: vi.fn() }
    meValue = { me: ADMIN, loading: false }
    renderAt('/dashboard/inicio')
    expect(await screen.findByRole('heading', { name: 'Conecte sua usina' })).toBeInTheDocument()
    expect(screen.queryByText('módulo início')).not.toBeInTheDocument()
  })

  it('quem só lê vê um aviso, sem formulário', async () => {
    plantValue = { plants: [], loading: false, error: null, reload: vi.fn() }
    meValue = { me: { ...ADMIN, role: 'READ' }, loading: false }
    renderAt('/dashboard/inicio')
    expect(await screen.findByText('Nenhuma usina conectada ainda')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Senha do app/)).not.toBeInTheDocument()
  })

  it('sem "quem sou eu" (carregando ou falhou), nada de formulário', async () => {
    plantValue = { plants: [], loading: false, error: null, reload: vi.fn() }
    meValue = { me: null, loading: true }
    const { unmount } = renderAt('/dashboard/inicio')
    expect(screen.getByRole('status')).toHaveTextContent('Carregando')
    expect(screen.queryByLabelText(/Senha do app/)).not.toBeInTheDocument()
    unmount()

    meValue = { me: null, loading: false }
    renderAt('/dashboard/inicio')
    expect(await screen.findByText('Nenhuma usina conectada ainda')).toBeInTheDocument()
  })

  it('com usina, mostra o módulo; Clientes não depende de usina', () => {
    plantValue = { plants: [{ id: 'p1', name: 'Casa' }], loading: false, error: null }
    meValue = { me: ADMIN, loading: false }
    renderAt('/dashboard/inicio')
    expect(screen.getByText('módulo início')).toBeInTheDocument()

    plantValue = { plants: [], loading: false, error: null }
    meValue = { me: { ...ADMIN, isPlatformOperator: true }, loading: false }
    renderAt('/dashboard/clientes')
    expect(screen.getByText('módulo clientes')).toBeInTheDocument()
  })

  it('aba Clientes só aparece para o dono da plataforma', () => {
    plantValue = { plants: [{ id: 'p1', name: 'Casa' }], loading: false, error: null }
    meValue = { me: ADMIN, loading: false }
    const { unmount } = renderAt('/dashboard/inicio')
    expect(screen.queryByRole('link', { name: 'Clientes' })).not.toBeInTheDocument()
    unmount()

    meValue = { me: { ...ADMIN, isPlatformOperator: true }, loading: false }
    renderAt('/dashboard/inicio')
    expect(screen.getByRole('link', { name: 'Clientes' })).toBeInTheDocument()
  })
})
