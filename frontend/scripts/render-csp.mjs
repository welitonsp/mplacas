// Sem shebang de propósito: `src/test/renderCsp.test.ts` importa este módulo, e
// o transform de builtins do Node feito pelo Vite hasteia os imports para o
// topo do arquivo — acima do shebang, produzindo sintaxe inválida. O script é
// invocado por `node scripts/render-csp.mjs` no build, então o shebang nunca
// foi usado.
// Resolve o marcador `__API_ORIGIN__` do CSP em `dist/_headers` usando a origem
// de `VITE_API_URL` (auditoria 2026-08-26, achado A-01).
//
// Por que isto existe: `_headers` é um arquivo estático do Cloudflare Pages e
// não lê variável de ambiente. Enquanto a origem da API ficou escrita à mão ali,
// ela sobreviveu à migração de plataforma apontando para um projeto do Google
// Cloud que havia sido excluído — e o efeito era o pior possível: a aplicação
// carregava, o navegador bloqueava todo `fetch` por violação de CSP, e não havia
// erro de servidor, log de API nem falha de CI apontando a causa.
//
// A origem do CSP e a origem que o cliente HTTP realmente chama passam a vir da
// MESMA variável, então não há como uma mudar sem a outra.
//
// Roda depois de `vite build`, nunca antes: sem `dist/_headers` (copiado de
// `public/` pelo Vite) não há o que reescrever.

import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

export const PLACEHOLDER = '__API_ORIGIN__'

/**
 * Extrai a origem (esquema + host + porta) de uma URL de API.
 * O CSP aceita origem, não caminho: `https://host/api` é inválido em `connect-src`.
 * Lança com mensagem acionável em vez de emitir um CSP quebrado.
 */
export function apiOrigin(rawUrl) {
  if (typeof rawUrl !== 'string' || rawUrl.trim() === '') {
    throw new Error('VITE_API_URL ausente ou vazia; não é possível montar o CSP')
  }
  let parsed
  try {
    parsed = new URL(rawUrl.trim())
  } catch {
    throw new Error(`VITE_API_URL não é uma URL válida: ${rawUrl}`)
  }
  if (parsed.protocol !== 'https:' && parsed.hostname !== 'localhost') {
    throw new Error(
      `VITE_API_URL deve usar HTTPS fora de localhost (recebido ${parsed.protocol})`
    )
  }
  return parsed.origin
}

/**
 * Substitui o marcador no template. Falha se o marcador não existir — isso
 * significa que alguém voltou a escrever a origem à mão, que é exatamente a
 * regressão que este script previne.
 */
export function renderHeaders(template, rawUrl) {
  if (!template.includes(PLACEHOLDER)) {
    throw new Error(
      `marcador ${PLACEHOLDER} não encontrado em _headers. A origem da API voltou a ` +
        'ser fixa no arquivo? Ver auditoria 2026-08-26, achado A-01.'
    )
  }
  const rendered = template.split(PLACEHOLDER).join(apiOrigin(rawUrl))
  if (rendered.includes(PLACEHOLDER)) {
    throw new Error('marcador remanescente após a substituição')
  }
  return rendered
}

function main() {
  const dirname = path.dirname(fileURLToPath(import.meta.url))
  const target = path.resolve(dirname, '..', 'dist', '_headers')

  let template
  try {
    template = readFileSync(target, 'utf-8')
  } catch {
    console.error(`Não encontrei ${target}. Rode este script depois de \`vite build\`.`)
    process.exit(1)
  }

  let rendered
  try {
    rendered = renderHeaders(template, process.env.VITE_API_URL)
  } catch (error) {
    console.error(`CSP não pôde ser gerado: ${error.message}`)
    console.error('O deploy foi interrompido de propósito: publicar um CSP incorreto')
    console.error('quebra todas as chamadas do dashboard sem gerar erro visível.')
    process.exit(1)
  }

  writeFileSync(target, rendered, 'utf-8')
  console.log(`CSP gerado: connect-src aponta para ${apiOrigin(process.env.VITE_API_URL)}`)
}

// Só executa quando invocado como CLI, para o teste poder importar as funções.
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  main()
}
