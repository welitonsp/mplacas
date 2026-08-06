import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { AppShell } from './AppShell'
import { useAuth } from '../contexts/AuthContext'
import { usePlant } from '../contexts/PlantContext'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../contexts/PlantContext', () => ({
  usePlant: vi.fn(),
}))

vi.mocked(useAuth).mockReturnValue({
  isAuthenticated: true,
  username: null,
  login: vi.fn(),
  logout: vi.fn(),
})

vi.mocked(usePlant).mockReturnValue({
  plantId: null,
  plants: [],
  loading: false,
  error: null,
  selectPlant: vi.fn(),
})

describe('AppShell — skip link', () => {
  it('o primeiro elemento focável é o skip link, e seu href aponta para o id do <main>', () => {
    const { container } = render(
      <AppShell>
        <p>conteúdo</p>
      </AppShell>
    )

    const focusable = container.querySelectorAll<HTMLElement>(
      'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    expect(focusable.length).toBeGreaterThan(0)

    const firstFocusable = focusable[0]
    expect(firstFocusable.tagName).toBe('A')
    expect(firstFocusable).toHaveTextContent('Pular para o conteúdo')

    const main = container.querySelector('main')
    expect(main).not.toBeNull()
    expect(firstFocusable.getAttribute('href')).toBe(`#${main!.id}`)
  })
})
