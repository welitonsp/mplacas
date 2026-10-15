// Garante que `designTokens.ts` (usado pelo teste de contraste) espelha o CSS
// real. Sem isto, mudar um hex em `index.css` e esquecer o espelho deixaria o
// teste de contraste aprovando cores que não são as da tela.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { DARK_TOKENS, LIGHT_TOKENS } from './designTokens'

const css = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf-8')

function bloco(inicio: string): string {
  const i = css.indexOf(inicio)
  expect(i).toBeGreaterThan(-1)
  return css.slice(i, css.indexOf('\n}', i))
}

const claro = bloco(':root {\n  --color-brand-primary')
const escuro = bloco(':root[data-theme="dark"] {')

describe.each([
  ['claro', claro, LIGHT_TOKENS] as const,
  ['escuro', escuro, DARK_TOKENS] as const,
])('espelho dos tokens — tema %s', (_nome, bloco, tokens) => {
  it.each(Object.entries(tokens))('%s bate com index.css', (nome, hex) => {
    const m = bloco.match(new RegExp(`${nome}:\\s*(#[0-9a-f]{6});`))
    expect(m?.[1]).toBe(hex)
  })
})
