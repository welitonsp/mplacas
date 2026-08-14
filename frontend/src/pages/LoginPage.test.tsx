import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo e lança se ausente — não há `.env.local` no ambiente de teste (é
// valor de configuração de deploy, não segredo versionado).
vi.mock('../env', () => ({
  API_URL: 'https://api.example.test',
}))

const { LoginPage } = await import('./LoginPage')
const { AuthProvider } = await import('../contexts/AuthContext')
const { TokenStore } = await import('../lib/auth')

function renderLoginPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>
  )
}

describe('LoginPage — acessibilidade e tokens de design', () => {
  it('mostra a proposta executiva e a prévia do cockpit no primeiro acesso', () => {
    renderLoginPage()

    expect(screen.getByText('Prévia do cockpit')).toBeInTheDocument()
    expect(screen.getByText('Operação, técnica e financeiro no mesmo olhar')).toBeInTheDocument()
    expect(screen.getByText('Sessão protegida por credenciais operacionais. O backend valida permissões a cada requisição.')).toBeInTheDocument()
  })

  it('o botão "Entrar" usa os tokens de cor do projeto, não classes bg-blue-*/focus:ring-blue-*', () => {
    renderLoginPage()

    const submitButton = screen.getByRole('button', { name: /entrar/i })
    expect(submitButton.className).not.toMatch(/bg-blue-|ring-blue-/)
    expect(submitButton.className).toMatch(/var\(--color-brand-primary\)/)
    expect(submitButton.className).toMatch(/focus-visible:ring/)
  })

  it('os campos de usuário e senha usam o token de foco do projeto', () => {
    renderLoginPage()

    const username = screen.getByLabelText('Usuário')
    const password = screen.getByLabelText('Senha')

    expect(username.className).not.toMatch(/focus:border-blue-|focus:ring-blue-/)
    expect(password.className).not.toMatch(/focus:border-blue-|focus:ring-blue-/)
    expect(username.className).toMatch(/var\(--color-brand-primary\)/)
  })
})

describe('LoginPage — toggle de senha', () => {
  it('alterna o type do input e o aria-pressed do botão ao clicar', () => {
    renderLoginPage()

    const password = screen.getByLabelText('Senha') as HTMLInputElement
    const toggle = screen.getByRole('button', { name: /mostrar/i })

    expect(password.type).toBe('password')
    expect(toggle).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(toggle)

    expect(password.type).toBe('text')
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /ocultar/i })).toBe(toggle)
  })
})

describe('LoginPage — redirecionamento declarativo quando já autenticado', () => {
  it('renderiza a rota de dashboard via <Navigate>, sem navigate() imperativo durante o render', () => {
    // `TokenStore.get()` decide `isAuthenticated` inicial no `AuthProvider` —
    // simulamos autenticação prévia gravando um token antes de montar.
    TokenStore.set('fake-token')

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/dashboard" element={<div>Dashboard</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )

    expect(screen.getByText('Dashboard')).toBeInTheDocument()

    TokenStore.clear()
  })
})

describe('LoginPage — anúncio acessível de carregamento (T10)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('anuncia "Entrando" por uma live region "polite" separada do botão, e volta a ficar em silêncio ao terminar', async () => {
    let resolveFetch: (value: Response) => void = () => {}
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>((resolve) => { resolveFetch = resolve }))
    )

    const { container } = renderLoginPage()

    const liveRegion = container.querySelector('[aria-live="polite"]') as HTMLElement
    expect(liveRegion).toBeInTheDocument()
    expect(liveRegion).toHaveTextContent('')

    fireEvent.change(screen.getByLabelText('Usuário'), { target: { value: 'operador' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'segredo123' } })

    const button = screen.getByRole('button', { name: /entrar/i })
    expect(button).toHaveAttribute('aria-busy', 'false')
    fireEvent.click(button)

    await waitFor(() => expect(liveRegion).toHaveTextContent('Entrando, aguarde.'))
    expect(screen.getByRole('button', { name: /entrando/i })).toHaveAttribute('aria-busy', 'true')

    // Caminho de erro (credenciais recusadas) mantém a página montada — evita
    // acoplar este teste ao redirecionamento de login bem-sucedido, que é
    // comportamento de outro conjunto de testes.
    resolveFetch(new Response(JSON.stringify({ detail: 'unauthorized' }), { status: 401 }))

    await waitFor(() => expect(liveRegion).toHaveTextContent(''))
    expect(screen.getByRole('button', { name: /entrar/i })).toHaveAttribute('aria-busy', 'false')
  })
})

describe('LoginPage — erro do formulário associado ao campo', () => {
  it('define aria-describedby nos campos apontando para o id da região de alerta', () => {
    renderLoginPage()

    const submitButton = screen.getByRole('button', { name: /entrar/i })
    fireEvent.click(submitButton)

    const alert = screen.getByRole('alert')
    const username = screen.getByLabelText('Usuário')
    const password = screen.getByLabelText('Senha')

    expect(username).toHaveAttribute('aria-describedby', alert.id)
    expect(password).toHaveAttribute('aria-describedby', alert.id)
  })

  // Auditoria v6, A-12. Esta asserção afirmava o oposto — que os campos
  // recebiam `aria-invalid="true"`. A premissa estava errada: todo erro desta
  // tela vem de `login()` (credencial recusada, excesso de tentativas, serviço
  // indisponível) e nenhum deles é de campo. Marcar ambos como inválidos
  // anunciava ao leitor de tela que os dois estavam malformados, mandando o
  // usuário procurar defeito onde não havia — inclusive quando o que falhou
  // foi o serviço, e não o que ele digitou.
  it('não marca campo como inválido quando o erro é global, não de campo', () => {
    renderLoginPage()

    fireEvent.click(screen.getByRole('button', { name: /entrar/i }))

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByLabelText('Usuário')).not.toHaveAttribute('aria-invalid')
    expect(screen.getByLabelText('Senha')).not.toHaveAttribute('aria-invalid')
  })
})

describe('LoginPage — aviso de sessão encerrada', () => {
  it('exibe aviso neutro quando location.state.reason é SESSION_ENDED', () => {
    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/login', state: { reason: 'SESSION_ENDED' } }]}
      >
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>
    )

    expect(screen.getByText('Sua sessão foi encerrada. Entre novamente.')).toBeInTheDocument()
  })

  it('não exibe o aviso quando não há reason no state', () => {
    renderLoginPage()

    expect(
      screen.queryByText('Sua sessão foi encerrada. Entre novamente.')
    ).not.toBeInTheDocument()
  })
})
