import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

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

// A-11 da auditoria v6: `aria-label` num `div` genérico. A role implícita de
// `div` não aceita nome acessível, então parte dos leitores de tela ignora o
// rótulo — o elemento fica sem nome, não com o nome pretendido.
describe('mockup do painel expõe nome acessível válido (A-11)', () => {
  const source = Object.values(sourceFiles).find((content) =>
    content.includes('dashboard-mockup')
  )

  it('a guarda encontrou o componente', () => {
    expect(source).toBeDefined()
  })

  it('o contêiner com aria-label declara role explícito', () => {
    // Casa a abertura da tag do mockup e exige que `role` apareça nela.
    const tag = /<div className="dashboard-mockup"([^>]*)>/.exec(source ?? '')
    expect(tag).not.toBeNull()
    expect(tag?.[1]).toContain('role=')
    expect(tag?.[1]).toContain('aria-label=')
  })
})

// Achado desta sessão (não estava na auditoria v6). `public-home.css` entra por
// chunk lazy junto de `PublicHomePage`, e CSS de chunk carregado NÃO é
// descarregado ao navegar. Uma regra em `:root` aqui, portanto, não fica na
// landing: acompanha o usuário para o painel e sobrescreve `index.css` no app
// inteiro — tipografia, cor e fundo.
describe('CSS da landing não vaza para o resto do app', () => {
  // Lido do disco, e não por `import.meta.glob('?raw')` como o resto deste
  // arquivo: o Vitest não processa CSS por padrão, então o import devolve
  // string VAZIA. A primeira versão desta guarda usava o glob e passava no
  // teste de "encontrou o arquivo" (`''` é `defined`) enquanto afirmava sobre
  // conteúdo nenhum — uma guarda que não podia falhar.
  const landingCss = readFileSync(
    resolve(process.cwd(), 'src/pages/public-home.css'),
    'utf-8'
  )

  it('a guarda está lendo conteúdo real, não string vazia', () => {
    expect(landingCss.length).toBeGreaterThan(500)
  })

  // Ampliado em 2026-08-27 (comparativo visual). A versão anterior verificava
  // SÓ `:root` — e passavam batido `html`, `body`, `*`, `a` e `button`, que têm
  // exatamente o mesmo alcance global. Seis regras assim vazavam para o painel,
  // incluindo `a { text-decoration: none }`, que removia o sublinhado de todo
  // link do app, e `body { background/color }` com variáveis definidas só em
  // `.site-shell`. Foi a captura visual do painel que expôs isso: o
  // `scroll-behavior: smooth` da landing deixava o menu instável no mobile.
  // Nome do seletor como aparece no CSS, e o mesmo já escapado para regex — o
  // `*` precisa virar `\*`, senão a expressão fica inválida.
  const SELETORES_GLOBAIS: ReadonlyArray<readonly [string, string]> = [
    [':root', ':root'],
    ['html', 'html'],
    ['body', 'body'],
    ['*', '\\*'],
    ['a', 'a'],
    ['button', 'button'],
  ]

  it.each(SELETORES_GLOBAIS)('nenhuma regra usa o seletor global `%s`', (_nome, escapado) => {
    // Só interessa seletor no INÍCIO de regra: comentários citam esses nomes em
    // prosa, e `.site-shell a` é justamente a forma correta e escopada.
    const padrao = new RegExp('^\\s*' + escapado + '\\s*[,{]')
    const rules = landingCss.split('\n').filter((line: string) => padrao.test(line))

    expect(rules).toEqual([])
  })

  it('as variáveis de tema vivem no contêiner da própria landing', () => {
    expect(landingCss).toMatch(/\.site-shell\s*\{[^}]*--navy:/)
  })
})
