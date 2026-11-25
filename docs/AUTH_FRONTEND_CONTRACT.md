# Contrato canônico de autenticação e frontend

Este documento é a fonte vigente para SPA, tokens, refresh, logout, rota de compatibilidade e
headers. ADR-012 foi substituída pela ADR-052; documentos históricos não podem redefinir este
contrato.

## Interface e roteamento

- A SPA React publicada no Cloudflare Pages é a única interface de usuário.
- FastAPI não serve HTML/JS/CSS do dashboard e nunca recebe `X-API-Key` de usuário pelo navegador.
- `GET /dashboard` no backend é somente um redirecionamento `308` temporário para
  `MPLACAS_DASHBOARD_URL`. `/dashboard-assets/*` não existe.

## Tokens

Decisão vigente: ADR-102 (substitui a ADR-073). Implantação em etapas; o que está marcado
**[transitório]** some na etapa 4 da ADR-102.

- O access token existe somente em memória JavaScript e dura 15 minutos.
- Nenhum token, senha ou chave é gravado em `localStorage`, `sessionStorage` ou URL. O único
  cookie permitido é o do refresh token, abaixo, que o JavaScript não lê.
- A única operação em `localStorage` com chave de credencial é remover, sem ler, a chave legada
  `mplacas_creds_v1`.
- **Cookie do refresh token:** `__Secure-mplacas_rt`, `HttpOnly; Secure; SameSite=Strict;
  Path=/api/auth` (configurável por `MPLACAS_AUTH_COOKIE_PATH`), `Max-Age` = tempo restante da
  sessão, nunca além do teto absoluto. Gravado por `POST /auth/login`, `POST /auth/refresh` e
  `POST /auth/invitations/accept` (convite e redefinição de acesso). Liga/desliga por
  `MPLACAS_AUTH_COOKIE_ENABLED` (padrão ligado).
- O refresh token rotaciona a cada uso. Replay revoga a família; reapresentar um token
  rotacionado há menos de 10 s (`MPLACAS_AUTH_REFRESH_REUSE_GRACE_SECONDS`) recebe 401 **sem**
  revogar a família (duas abas). A família nunca passa de 30 dias desde o login
  (`MPLACAS_AUTH_SESSION_MAX_AGE_DAYS`); depois disso, 401 e login com senha.
- `POST /auth/refresh` lê o cookie primeiro; com cookie, ele é a credencial e o corpo é ignorado.
  Refresh recusado pelo cookie apaga o cookie, exceto na tolerância de duas abas (401 sem
  `Set-Cookie`).
  **[transitório]** Sem cookie, aceita `{"refresh_token": ...}` no corpo, como antes.
- **[transitório]** As respostas de login, refresh e aceite ainda trazem `refresh_token` no corpo
  JSON. Desde a etapa 3 o frontend **ignora** esse campo: não o lê, não o guarda e não o envia.
  O teste de contrato proíbe `refresh_token`/`refreshToken` e `document.cookie` no código de
  aplicação de `frontend/src`.

## Frontend (etapa 3 da ADR-102)

- Base da API: sempre `/api` (`frontend/src/env.ts`), a própria origem. `VITE_API_URL` deixou de
  existir no frontend; o build falha se ela estiver no ambiente (`scripts/render-csp.mjs`). Em
  desenvolvimento, o `vite dev` repassa `/api` para `MPLACAS_DEV_API_ORIGIN` (padrão
  `http://localhost:8000`); a origem `http://localhost:5173` precisa estar em
  `MPLACAS_CORS_ALLOWED_ORIGINS` do backend local.
- Todo pedido usa `credentials: 'same-origin'`. Pedidos de autenticação (login, refresh, logout,
  convite — `frontend/src/lib/session.ts`) mandam também `X-Mplacas-Auth: 1` e
  `referrerPolicy: 'same-origin'`: a página usa `Referrer-Policy: no-referrer`, e com ela a
  especificação do Fetch manda `Origin: null` em POST para a própria origem, que o backend recusa.
- `POST /auth/refresh` vai **sem corpo**; a credencial é o cookie.
- **Ao carregar o app** (F5, link direto, aba nova) sem access token em memória, o `AuthProvider`
  chama `/auth/refresh` antes de qualquer rota protegida decidir. Enquanto isso a rota protegida
  mostra "Conectando…"; depois de 10 s, "O servidor está acordando, pode levar até um minuto".
  - `200` → adota o access token (memória) e segue no link aberto;
  - `401`/outros `4xx`/`200` malformado → login, com `state.from`; "Sua sessão foi encerrada" só
    quando **esta aba** tinha sessão e o refresh foi recusado;
  - falha de rede, prazo, `5xx` (inclui `502/503/504` do proxy), `408`, `429` → "Tentar de novo",
    nunca o login (a sessão pode estar viva e o servidor acordando).
- Refresh serializado entre abas com `navigator.locks.request('mplacas-refresh', …)`; sem Web Locks,
  vale o single-flight da aba. Um `401` do refresh é repetido **uma** vez após 300 ms (outra aba
  acabou de rotacionar — tolerância do backend).
- `apiFetch` tenta um único refresh após 401 e repete a requisição uma única vez. Refresh recusado
  encerra a sessão local ("sessão encerrada"); refresh inalcançável **não** desloga: a chamada
  falha com `SessionRefreshUnavailableError` e a tela oferece nova tentativa.

## Defesa CSRF

- Pedido autenticado pelo cookie (`/auth/refresh`, `/auth/logout`) exige `X-Mplacas-Auth: 1` **e**
  `Origin` igual a uma origem de `MPLACAS_CORS_ALLOWED_ORIGINS`. Falhou → `403`, sem rotacionar,
  revogar nem apagar o cookie.
- `POST /auth/login` e `POST /auth/invitations/accept`: se houver `Origin`, ele precisa estar na
  lista (senão `403`); sem `Origin` (cliente que não é navegador), segue como antes.
  **Atenção:** com `MPLACAS_CORS_ALLOWED_ORIGINS` vazia, todo login e aceite feito por navegador
  (que sempre manda `Origin`) recebe `403`, e o refresh/logout pelo cookie também. A lista precisa
  conter a origem exata do frontend em todo ambiente com navegador.
- O fluxo do corpo, sem cookie, não exige cabeçalho novo **[transitório]**.

## Logout

O frontend primeiro limpa o access token em memória e muda o estado local para desautenticado.
Envia `POST /auth/logout` sem corpo, com `keepalive`, `credentials: 'same-origin'` e
`X-Mplacas-Auth: 1` (pelo mesmo lock do refresh); falha de rede não restaura a sessão local. O endpoint é
idempotente, sempre responde `204` para token inválido, expirado, já revogado ou válido, e revoga a
sessão persistida quando consegue autenticar o refresh token. Com o cookie, revoga e responde com o
cookie apagado (`Max-Age=0`, mesmo `Path` e atributos); **[transitório]** sem cookie, aceita
`{"refresh_token": ...}` no corpo. Access tokens já emitidos continuam válidos até o TTL, conforme
decisão explícita da ADR-052.

## Proxy e IP do cliente

- Etapa 2 da ADR-102: Cloudflare Pages Function em `mplacas-frontend.pages.dev/api/*`
  (`frontend/functions/api/[[path]].ts`, lógica e testes em `frontend/edge/apiProxy.ts`) repassa
  ao backend tirando o prefixo `/api`. Para o navegador, a API passa a ser same-origin.
  - `frontend/public/_routes.json` = `{"version":1,"include":["/api/*"],"exclude":[]}`: arquivos
    estáticos nunca acionam a Function (nem gastam a cota gratuita).
  - Configuração no Cloudflare Pages (produção): `MPLACAS_API_ORIGIN` (origem `https` exata do
    Render, sem caminho) e `MPLACAS_PROXY_SHARED_SECRET` (≥ 32 bytes, igual ao do Render). Faltando
    ou inválida qualquer uma → `503 {"detail":"service unavailable"}` em todo `/api/*` (falha
    fechada: sem o segredo, o backend veria todos os clientes com o IP da Cloudflare e o bloqueio
    de tentativas de login viraria arma contra a vítima).
  - Cabeçalhos repassados (lista fechada): `Accept`, `Accept-Language`, `Authorization`,
    `Content-Type`, `Cookie`, `If-Match`, `If-Modified-Since`, `If-None-Match`, `Origin`,
    `X-Mplacas-Auth`, `X-Request-Id`. Hop-by-hop, `Referer`, `X-Forwarded-*` e os
    `X-Mplacas-Client-IP`/`X-Mplacas-Proxy-Secret` enviados pelo cliente são descartados.
  - Resposta: status, corpo (em fluxo) e cabeçalhos, com cada `Set-Cookie` preservado separado;
    `Server`, `Via`, `X-Powered-By`, `X-Render-*`, `Rndr-*`, `CF-*` e hop-by-hop não voltam;
    `Location` do próprio backend vira `/api/...`.
  - Backend sem resposta em 58 s → `504` genérico (o cliente desiste em 60 s); falha de conexão →
    `502` genérico. Nenhum log de cabeçalho, cookie, corpo ou segredo.
- O proxy envia `X-Mplacas-Client-IP` (do `CF-Connecting-IP`) com `X-Mplacas-Proxy-Secret`; o
  backend só honra o IP quando o segredo confere com `MPLACAS_PROXY_SHARED_SECRET` (sem segredo
  configurado, o cabeçalho é ignorado). O segredo nunca é logado.
- **[transitório]** `MPLACAS_FORWARDED_ALLOW_IPS=*` (padrão) mantém o comportamento anterior, com
  XFF forjável. A saída é `MPLACAS_TRUSTED_PROXY_HOPS` (IP = `XFF[-N]`), definido depois de ler o
  log `client_ip_diagnostic` — procedimento na ADR-102 § 6.

## Headers e origens

Cloudflare Pages aplica `_headers`: CSP, HSTS, `nosniff`, `DENY`, `no-referrer`,
Permissions-Policy, COOP e CORP. Desde a ADR-102 o CSP é `connect-src 'self'` — nenhum host
externo, nenhum `https:` genérico; a API chega pelo proxy `/api`. `scripts/render-csp.mjs` falha o
build se o `connect-src` do `dist/_headers` não for exatamente esse. O backend aplica seus headers
defensivos e CORS com lista exata de origens HTTPS. Wildcard `*.pages.dev` não é aceito.

O HTML conserva o padrão Pages `max-age=0, must-revalidate`. Somente `/assets/*`, cujos nomes
incluem hash de conteúdo gerado pelo Vite, recebe `max-age=31536000, immutable`; não criar regra
global de cache que possa servir HTML obsoleto após deploy.

Qualquer mudança de armazenamento, TTL, refresh, logout, CSP ou CORS exige atualização deste
contrato, ADR aplicável e testes antes do deploy.
