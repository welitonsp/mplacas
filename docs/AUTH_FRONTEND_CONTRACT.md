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
  JSON. Até a etapa 3, o frontend guarda esse valor só em memória (nunca em storage).
- `apiFetch` tenta um único refresh após 401 e repete a requisição uma única vez. Com o cookie
  (etapa 3), um 401 do próprio refresh pode ser repetido uma vez (outra aba acabou de rotacionar).

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

O frontend primeiro limpa os tokens em memória e muda o estado local para desautenticado. Envia
`POST /auth/logout` com `keepalive`; falha de rede não restaura a sessão local. O endpoint é
idempotente, sempre responde `204` para token inválido, expirado, já revogado ou válido, e revoga a
sessão persistida quando consegue autenticar o refresh token. Com o cookie, revoga e responde com o
cookie apagado (`Max-Age=0`, mesmo `Path` e atributos); **[transitório]** sem cookie, aceita
`{"refresh_token": ...}` no corpo. Access tokens já emitidos continuam válidos até o TTL, conforme
decisão explícita da ADR-052.

## Proxy e IP do cliente

- Etapa 2 da ADR-102: Cloudflare Pages Function em `mplacas-frontend.pages.dev/api/*` repassa ao
  backend, preservando `Origin`, `Cookie`, `Set-Cookie` e `X-Mplacas-Auth`. Para o navegador, a
  API passa a ser same-origin.
- O proxy envia `X-Mplacas-Client-IP` (do `CF-Connecting-IP`) com `X-Mplacas-Proxy-Secret`; o
  backend só honra o IP quando o segredo confere com `MPLACAS_PROXY_SHARED_SECRET` (sem segredo
  configurado, o cabeçalho é ignorado). O segredo nunca é logado.
- **[transitório]** `MPLACAS_FORWARDED_ALLOW_IPS=*` (padrão) mantém o comportamento anterior, com
  XFF forjável. A saída é `MPLACAS_TRUSTED_PROXY_HOPS` (IP = `XFF[-N]`), definido depois de ler o
  log `client_ip_diagnostic` — procedimento na ADR-102 § 6.

## Headers e origens

Cloudflare Pages aplica `_headers`: CSP, HSTS, `nosniff`, `DENY`, `no-referrer`,
Permissions-Policy, COOP e CORP. O `connect-src` permite somente a própria origem e o hostname
canônico do backend Cloud Run; `https:` genérico é proibido. O backend aplica seus headers
defensivos e CORS com lista exata de origens HTTPS. Wildcard `*.pages.dev` não é aceito.

O HTML conserva o padrão Pages `max-age=0, must-revalidate`. Somente `/assets/*`, cujos nomes
incluem hash de conteúdo gerado pelo Vite, recebe `max-age=31536000, immutable`; não criar regra
global de cache que possa servir HTML obsoleto após deploy.

Qualquer mudança de armazenamento, TTL, refresh, logout, CSP ou CORS exige atualização deste
contrato, ADR aplicável e testes antes do deploy.
