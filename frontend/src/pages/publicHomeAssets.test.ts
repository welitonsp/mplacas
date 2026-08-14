import { describe, expect, it } from 'vitest'

// Guarda de origem externa na página pública (auditoria v6, achados A-16/A-15).
//
// O que aconteceu: a landing entrou carregando fotografia do Unsplash e fontes
// do Google Fonts, mas a CSP do projeto (`frontend/public/_headers`) é
// bloqueante e restrita à própria origem — `img-src 'self' data:`,
// `style-src 'self'`, `font-src 'self'`. O resultado ficou visível em
// produção: herói sem imagem e tipografia de fallback. Nada no processo pegou,
// porque nenhum teste olhava para a fronteira entre o que a página carrega e o
// que a política permite.
//
// A correção foi auto-hospedar em vez de afrouxar a CSP: resolve os dois
// achados de uma vez e tira terceiros do caminho crítico da página pública.
// Esta guarda existe para que a próxima adição de asset externo falhe aqui, e
// não em produção.
const sourceFiles = import.meta.glob('/src/pages/*.{ts,tsx,css}', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

const htmlFiles = import.meta.glob('/index.html', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

// Hosts de terceiros que a CSP atual não permite. Acrescentar um host aqui é
// mais barato do que descobrir em produção que a política o bloqueia.
const FORBIDDEN_HOSTS = [
  'images.unsplash.com',
  'fonts.googleapis.com',
  'fonts.gstatic.com',
]

function offendersIn(files: Record<string, string>): string[] {
  return Object.entries(files).flatMap(([path, content]) =>
    FORBIDDEN_HOSTS.filter(
      // A própria prosa desta guarda e os comentários que explicam a correção
      // citam os hosts; só interessa referência dentro de URL.
      (host) => content.includes(`https://${host}`)
    ).map((host) => `${path}: ${host}`)
  )
}

describe('página pública não carrega origem externa bloqueada pela CSP', () => {
  it('a guarda está lendo os arquivos reais', () => {
    expect(Object.keys(sourceFiles).length).toBeGreaterThan(0)
    expect(Object.keys(htmlFiles).length).toBe(1)
  })

  it('nenhum arquivo de `src/pages/` referencia host de terceiro', () => {
    expect(offendersIn(sourceFiles)).toEqual([])
  })

  it('o `index.html` não carrega fonte nem asset externo', () => {
    expect(offendersIn(htmlFiles)).toEqual([])
  })
})
