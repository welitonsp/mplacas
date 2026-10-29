import { describe, expect, it } from 'vitest'

// Escala tipográfica do painel (refinamento ADR-077, auditoria visual de
// 28/10/2026, item 14 — ver o bloco `@theme` em `index.css`). Os degraus
// nomeados vêm das classes do Tailwind reapontadas (`text-xs` 12, `text-sm`/
// `text-base` 15, `text-lg`/`text-xl` 18, `text-2xl` 24, `text-3xl` 28). Fora
// deles, só estes tamanhos arbitrários existem de propósito:
//   13 — texto de apoio; 28 — número grande; 34 — título da página (`h1`);
//   40 — o valor de economia do Início.
// O login tem o seu título de 56 px no desktop (fora do painel).
const ALLOWED = new Set([13, 28, 34, 40])
const LOGIN_ONLY = new Set([56])

const sources = import.meta.glob(['./**/*.tsx', '../pages/**/*.tsx', '../lib/dashboard/visuals.ts'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const files = Object.entries(sources).filter(([path]) => !path.includes('.test.'))

describe('escala tipográfica — nenhum tamanho arbitrário fora da escala', () => {
  it.each(files)('%s usa só tamanhos da escala', (path, content) => {
    const outside = [...content.matchAll(/text-\[(\d+)px\]/g)]
      .map((match) => Number(match[1]))
      .filter((size) => !ALLOWED.has(size) && !(path.endsWith('LoginPage.tsx') && LOGIN_ONLY.has(size)))
    expect(outside).toEqual([])
  })
})
