import { describe, expect, it } from 'vitest'
import dashboardPageSource from './DashboardPage.tsx?raw'

// `DashboardPage` faz fetch de dados reais no mount (executivo, produção
// esperada, anomalias), então um teste de render completo exigiria mockar
// três chamadas de rede só para inspecionar uma classe CSS estática. Como a
// própria tarefa autoriza checagem "via snapshot de classe" para foco
// visível (jsdom não renderiza foco de verdade), fazemos a checagem
// diretamente na fonte do botão "Atualizar".
describe('DashboardPage — botão "Atualizar" tem foco visível', () => {
  it('a className do botão "Atualizar" inclui focus-visible:ring', () => {
    const buttonMatch = dashboardPageSource.match(
      /\{loading \? 'Atualizando\.\.\.' : 'Atualizar'\}/
    )
    expect(buttonMatch).not.toBeNull()

    // A className do botão está na linha imediatamente anterior ao texto.
    const buttonBlockStart = dashboardPageSource.lastIndexOf('<button', buttonMatch!.index)
    const buttonBlock = dashboardPageSource.slice(buttonBlockStart, buttonMatch!.index)
    expect(buttonBlock).toMatch(/focus-visible:ring/)
  })
})
