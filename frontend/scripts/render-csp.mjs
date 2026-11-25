// Sem shebang de propósito: `src/test/renderCsp.test.ts` importa este módulo, e
// o transform de builtins do Node feito pelo Vite hasteia os imports para o
// topo do arquivo — acima do shebang, produzindo sintaxe inválida. O script é
// invocado por `node scripts/render-csp.mjs` no build.
//
// Guarda do CSP depois do `vite build` (ADR-102).
//
// Histórico: este script resolvia o marcador `__API_ORIGIN__` do CSP com a
// origem de `VITE_API_URL` (auditoria 2026-08-26, achado A-01 — uma origem
// escrita à mão sobreviveu à migração de plataforma e o navegador bloqueava
// todo `fetch` sem erro visível). Desde a ADR-102 o navegador só fala com a
// própria origem: a API é `/api/*`, repassada ao Render pela Pages Function.
// O CSP passa a ser fixo, `connect-src 'self'`, e não há mais origem a montar.
//
// O que o script garante agora, falhando o build:
// 1. `dist/_headers` tem `connect-src 'self'` e nenhuma origem externa nele
//    (alguém reintroduzir uma API de outra origem quebraria o cookie da sessão,
//    `SameSite=Strict`, sem erro visível);
// 2. nenhum marcador antigo sobrou;
// 3. `VITE_API_URL` não está definida no ambiente do build: ela deixou de ser
//    lida, e mantê-la configurada faria alguém achar que aponta a API para
//    algum lugar.

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

export const LEGACY_PLACEHOLDER = '__API_ORIGIN__'
export const EXPECTED_CONNECT_SRC = "connect-src 'self';"

/** Lança se o CSP do `_headers` não for exatamente same-origin no `connect-src`. */
export function assertSameOriginCsp(headers) {
  if (headers.includes(LEGACY_PLACEHOLDER)) {
    throw new Error(
      `marcador ${LEGACY_PLACEHOLDER} encontrado em _headers: desde a ADR-102 o CSP é ` +
        `fixo (${EXPECTED_CONNECT_SRC}) e a API passa pelo proxy /api.`
    )
  }
  const directives = headers.match(/connect-src[^;\n]*;?/g) ?? []
  if (directives.length !== 1 || directives[0] !== EXPECTED_CONNECT_SRC) {
    throw new Error(
      `CSP inesperado: esperado exatamente "${EXPECTED_CONNECT_SRC}", encontrado ` +
        `${JSON.stringify(directives)}. A API deve ser a própria origem (proxy /api, ADR-102).`
    )
  }
}

/** Lança se a variável aposentada ainda estiver configurada no build. */
export function assertNoLegacyApiUrl(env) {
  const value = env.VITE_API_URL
  if (typeof value === 'string' && value.trim() !== '') {
    throw new Error(
      'VITE_API_URL está definida, mas deixou de ser lida (ADR-102): o frontend chama ' +
        'sempre /api, e quem aponta para o Render é a variável MPLACAS_API_ORIGIN do ' +
        'Cloudflare Pages. Remova VITE_API_URL do ambiente do build.'
    )
  }
}

function main() {
  const dirname = path.dirname(fileURLToPath(import.meta.url))
  const target = path.resolve(dirname, '..', 'dist', '_headers')

  let headers
  try {
    headers = readFileSync(target, 'utf-8')
  } catch {
    console.error(`Não encontrei ${target}. Rode este script depois de \`vite build\`.`)
    process.exit(1)
  }

  try {
    assertNoLegacyApiUrl(process.env)
    assertSameOriginCsp(headers)
  } catch (error) {
    console.error(`CSP recusado: ${error.message}`)
    process.exit(1)
  }

  console.log(`CSP conferido: ${EXPECTED_CONNECT_SRC} (API pelo proxy /api)`)
}

// Só executa quando invocado como CLI, para o teste poder importar as funções.
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  main()
}
