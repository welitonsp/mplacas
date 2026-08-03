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

- Access e refresh tokens existem somente em memória JavaScript; recarregar a página exige login.
- Nenhum token, senha ou chave é gravado em `localStorage`, `sessionStorage`, URL ou cookie.
- A única operação em `localStorage` é remover, sem ler, a chave legada `mplacas_creds_v1`.
- O access token dura 15 minutos. O refresh token rotaciona a cada uso e replay revoga a família.
- `apiFetch` tenta um único refresh após 401 e repete a requisição uma única vez.

## Logout

O frontend primeiro limpa ambos os tokens em memória e muda o estado local para desautenticado.
Se havia refresh token, envia `POST /auth/logout` com `keepalive`; falha de rede não restaura a
sessão local. O endpoint é idempotente, sempre responde `204` para token inválido, expirado, já
revogado ou válido, e revoga a sessão persistida quando consegue autenticar o refresh token.
Access tokens já emitidos continuam válidos até o TTL, conforme decisão explícita da ADR-052.

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
