import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL`/`VITE_PLANT_ID` no
// carregamento do módulo e lança se ausentes — não há `.env.local` no ambiente
// de teste (são valores de configuração de deploy, não segredos versionados).
vi.mock('../env', () => ({
  API_URL: 'https://api.example.test',
  PLANT_ID: '00000000-0000-0000-0000-000000000000',
}))

const { LoginPage } = await import('./LoginPage')
const { AuthProvider } = await import('../contexts/AuthContext')

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
