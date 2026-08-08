import { describe, expect, it } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { useModuleTitle } from './useModuleTitle'

// Componente mínimo que exercita o hook do jeito que cada módulo do painel
// (`pages/dashboard/*.tsx`) o usa de verdade: aplica o `ref` devolvido a um
// `<h1 tabIndex={-1}>` real.
function ModuleStub({ title }: { title: string }) {
  const headingRef = useModuleTitle(title)
  return (
    <h1 ref={headingRef} tabIndex={-1}>
      {title}
    </h1>
  )
}

describe('useModuleTitle', () => {
  it('define document.title como "Mplacas — <título>" ao montar', async () => {
    render(<ModuleStub title="Visão Geral" />)

    await waitFor(() => {
      expect(document.title).toBe('Mplacas — Visão Geral')
    })
  })

  it('move o foco para o <h1> associado ao ref ao montar', async () => {
    const { getByRole } = render(<ModuleStub title="Produção" />)

    const heading = getByRole('heading', { level: 1, name: 'Produção' })
    await waitFor(() => {
      expect(heading).toHaveFocus()
    })
  })

  it('ao trocar de módulo (remontagem, como acontece navegando entre rotas), título e foco refletem o módulo novo', async () => {
    const { getByRole, unmount } = render(<ModuleStub title="Financeiro" />)
    await waitFor(() => {
      expect(document.title).toBe('Mplacas — Financeiro')
    })
    unmount()

    const { getByRole: getByRoleAfter } = render(<ModuleStub title="Técnico" />)
    await waitFor(() => {
      expect(document.title).toBe('Mplacas — Técnico')
    })
    const heading = getByRoleAfter('heading', { level: 1, name: 'Técnico' })
    await waitFor(() => {
      expect(heading).toHaveFocus()
    })

    // Sanity check: a busca pelo heading antigo não encontra mais nada
    // (componente anterior já desmontou).
    expect(() => getByRole('heading', { level: 1, name: 'Financeiro' })).toThrow()
  })
})
