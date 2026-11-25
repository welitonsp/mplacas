// Base da API (ADR-102). O navegador só conversa com a própria origem: em
// produção, a Cloudflare Pages Function `functions/api/[[path]].ts` repassa
// `/api/*` ao backend no Render; em desenvolvimento, o proxy do `vite dev`
// (`vite.config.ts`, alvo em `MPLACAS_DEV_API_ORIGIN`) faz o mesmo papel.
//
// Por que caminho fixo e não `VITE_API_URL`: o cookie da sessão é
// `SameSite=Strict` com `Path=/api/auth` e só existe se a API for a mesma
// origem do site; a CSP é `connect-src 'self'`. Uma URL absoluta de outra
// origem quebraria as duas coisas sem erro visível. `VITE_API_URL` deixou de
// ser lida; o build falha se ela ainda estiver definida (`scripts/render-csp.mjs`),
// para ninguém achar que está configurando algo que não tem efeito.
export const API_URL = '/api'
