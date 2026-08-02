# ADR-012 — Dashboard web responsivo

## Status

Substituído pela ADR-052 em 2026-08-01.

## Contexto

A decisão original servia HTML, CSS e JavaScript pela FastAPI e previa uma chave operacional
somente em memória. A implementação posterior passou a persistir essa chave em
`localStorage`, divergindo da ADR e criando um segundo modelo de autenticação ao lado da SPA
React autenticada por JWT.

## Decisão vigente

- A SPA React hospedada separadamente é a única interface de usuário.
- A SPA usa JWT; access token e refresh token permanecem somente em memória.
- Nenhum fluxo de usuário solicita ou persiste `X-API-Key`.
- `GET /dashboard` existe apenas como redirecionamento permanente para a SPA configurada em
  `MPLACAS_DASHBOARD_URL`.
- `/dashboard-assets` e os assets estáticos legados foram removidos.
- Durante a migração, a SPA apaga `localStorage.mplacas_creds_v1` sem ler ou transmitir o valor.
- A borda da SPA e a API publicam CSP/headers defensivos compatíveis com suas responsabilidades.
- Regras e cálculos energéticos continuam exclusivamente no backend determinístico.

## Consequências

Existe um único modelo de autenticação para usuários, a superfície de XSS com credencial de
longa duração é eliminada e clientes antigos continuam chegando ao produto pelo redirecionamento.
A rota de compatibilidade pode ser removida após o período de migração.
