// Guarda do achado V-1 do comparativo visual de 2026-08-27.
//
// As fontes Manrope e Space Grotesk estavam baixadas em `public/fonts/` e
// declaradas SÓ em `pages/public-home.css`, que carrega apenas na página
// pública. O resultado: a landing tinha tipografia desenhada e o PRODUTO
// renderizava em `system-ui` — o sinal isolado mais forte de "sistema
// inacabado" na comparação com projetos equivalentes do GitHub.
//
// Ninguém notou por dois anos de commits porque nada no fluxo de trabalho
// mostra a tela para alguém (achado V-5). Enquanto não houver captura visual no
// CI, estas asserções sobre o CSS são a única rede de proteção.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

// Lido do disco, não por import: o Vitest não processa CSS por padrão e o
// import devolveria string vazia — a mesma armadilha que publicHomeAssets.test
// documenta, onde uma guarda passava afirmando sobre conteúdo nenhum.
const globalCss = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf-8')
const headers = readFileSync(resolve(process.cwd(), 'public/_headers'), 'utf-8')

describe('tipografia da interface', () => {
  it('a guarda está lendo conteúdo real, não string vazia', () => {
    expect(globalCss.length).toBeGreaterThan(500)
  })

  it('o produto usa Manrope, não a fonte padrão do sistema', () => {
    // A vírgula é o que distingue a PILHA de fontes da interface das
    // declarações `@font-face`, que nomeiam uma família só. Sem ela o regex
    // casa com a primeira @font-face e a asserção vira ruído.
    const regra = globalCss.match(/font-family:\s*'Manrope',[^;]*;/)

    expect(regra).not.toBeNull()
    // `system-ui` continua no fim da pilha, como fallback enquanto a fonte
    // carrega e se ela falhar — o que não pode voltar é ele ser o primeiro.
    expect(regra?.[0]).toContain('system-ui')
    expect(regra?.[0]).not.toMatch(/font-family:\s*system-ui/)
  })

  it('declara os quatro pesos que o app realmente usa', () => {
    // font-normal(400), font-medium(500), font-semibold(600), font-bold(700).
    // Um peso ausente seria sintetizado ou cairia no fallback, quebrando o
    // ritmo tipográfico de forma difícil de perceber.
    for (const peso of [400, 500, 600, 700]) {
      expect(globalCss).toMatch(
        new RegExp(`font-family:\\s*'Manrope';[\\s\\S]{0,120}font-weight:\\s*${peso};`)
      )
    }
  })

  it('permite sintetizar itálico, mas nunca peso', () => {
    // Não há arquivo itálico de Manrope. Com `font-synthesis: none` o
    // disclaimer em AiExplanationPanel.tsx perderia o itálico em silêncio.
    // Peso segue proibido de síntese: os quatro são reais e sintetizar
    // produziria bold falso e mais pesado que o desenhado.
    expect(globalCss).toMatch(/font-synthesis:\s*style;/)
    expect(globalCss).not.toMatch(/font-synthesis:\s*none;/)
  })

  it('as fontes têm cache longo — são ~97 kB por visita sem ele', () => {
    // Os arquivos ficam em `public/fonts/` e NÃO recebem hash de conteúdo do
    // Vite, ao contrário de `/assets/*`. Sem regra explícita o navegador
    // revalida a cada visita. `immutable` implica que trocar uma fonte exige
    // trocar o nome do arquivo.
    expect(headers).toMatch(/\/fonts\/\*\s*\n\s*Cache-Control: public, max-age=31536000, immutable/)
  })
})
