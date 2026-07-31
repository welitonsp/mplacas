# ADR-052 — Evolução SaaS: Multitenancy com Organizações, JWT e Frontend Cloudflare

## Status

Aceito.

## Contexto

O Mplacas nasceu como sistema single-tenant operado por chave de API (ADR-045). À medida que o produto
evoluiu para atender múltiplos usuários com usinas independentes, a arquitetura precisou suportar:

1. **Banco gerenciado remoto** — SQLite local não escala para múltiplos clientes nem para deploys
   redundantes no Cloud Run.
2. **Isolamento por organização** — cada grupo de usinas deve estar associado a uma organização,
   com credenciais e usuários próprios.
3. **Autenticação com identidade** — usuários finais não devem operar com a chave administrativa
   compartilhada `MPLACAS_OPERATIONS_API_KEY`.
4. **Frontend desacoplado** — o dashboard web deve ser servido por CDN independente do Cloud Run
   para reduzir latência e custo.

Essas quatro necessidades foram implementadas em quatro fases incrementais (Phase 0–3), cada uma
entregue em PR própria com escopo fechado e CI verde.

## Decisão

### Phase 0 — Neon PostgreSQL como banco gerenciado (ver ADR-051)

Adotar Neon como provedor PostgreSQL gerenciado para produção e staging. O free tier cobre o volume
inicial; database branching substitui ambientes de staging completos.

Configuração de conexão:

- SSL obrigatório via `connect_args={"ssl": "require"}` quando `neon.tech` está na URL.
- Pool conservador para o free tier: `pool_size=3, max_overflow=2` (pico de 5 conexões).
- URL normalizada automaticamente por `Settings._normalize_database_url`
  (`postgres://` → `postgresql+asyncpg://`).

### Phase 1 — Tabela `organizations` e FK de isolamento

Criar a entidade `Organization` (id, name, slug, active, deactivated_at) como raiz de agregação
para usinas, usuários e credenciais.

Migrações aplicadas:

| Migração | Conteúdo |
|---|---|
| `0019` | Tabela `organizations` |
| `0020` | Coluna `organization_id` nullable em `plants`, `operational_users`, `api_credentials` |
| `0021` | Backfill: um usuário existente sem organização recebe organização padrão; usinas/credenciais órfãs seguem a mesma |
| `0022` | `ALTER COLUMN organization_id SET NOT NULL` no banco; ORM mantém nullable durante transição de testes |

Invariante: toda usina, usuário operacional e credencial de API pertence a exatamente uma organização.

### Phase 2 — JWT, argon2id e Bearer token

Substituir a chave operacional única por autenticação com identidade:

- **`POST /auth/login`**: recebe `username` + `password`, retorna `access_token` (JWT HS256, TTL
  15 min) e `refresh_token` (JWT HS256, TTL 14 dias). Senha verificada com argon2id.
- **`POST /auth/refresh`**: recebe `refresh_token` no body, emite novo `access_token`.
- **`security.py`**: `require_operations_key` e `require_operations_read` passam a aceitar
  `Authorization: Bearer <token>` além da chave legada, mantendo retrocompatibilidade com
  integrações existentes.
- **CORS**: `CORSMiddleware` configurado por `MPLACAS_CORS_ALLOWED_ORIGINS` (lista de origens
  separadas por vírgula, cada uma validada por `infra/gcp/lib.sh:validate_cors_origins`).
- **Migração `0023`**: coluna `password_hash VARCHAR(255) NULL` em `operational_users`.

Decisão de segurança: argon2id (via `argon2-cffi`) é o KDF recomendado pelo OWASP para hash de
senhas em 2025. O hash nunca aparece em logs, respostas ou trilha de auditoria.

### Phase 2b — Sessões de auth, rate limit de login e papéis (migration `0024`)

Adicionado após a Phase 2 original para fechar a lacuna de revogação de refresh token:

- **Tabela `auth_sessions`**: uma linha por refresh token emitido, com `refresh_token_hash`
  (nunca o token em claro), `expires_at`, `rotated_at`, `revoked_at` e
  `replaced_by_session_id` (encadeia a rotação). `organization_id` é FK direta, não derivada —
  cada sessão pertence a exatamente uma organização.
- **`SessionService.revoke(session_id)`** (`auth/session_service.py`): revogação explícita de
  sessão, usada em rotação de refresh token e logout. `POST /auth/refresh` rejeita reuso de um
  refresh token já rotacionado/revogado.
- **Tabela `login_rate_limits`**: bloqueio por chave (`key`, tipicamente usuário+IP) com
  `locked_until`, mitigando força bruta em `POST /auth/login`.
- **Coluna `role`** em `operational_users` (`String(16)`, default `ADMIN` por retrocompatibilidade
  com usuários existentes).

Isso resolve o item de "Próximos passos" original sobre invalidação de refresh tokens — não é
mais um item pendente, é uma tabela dedicada (`auth_sessions`), não uma lista de revogação em
Redis como o texto original desta seção especulava.

### Phase 3 — React SPA no Cloudflare Pages

SPA construída com React 19 + TypeScript + Vite + Tailwind CSS 4, publicada no Cloudflare Pages:

- **Auth**: access token em `localStorage` (TTL curto de 15 min); refresh token em memória (perdido
  ao fechar ou recarregar a aba). `apiFetch` renova automaticamente com retry único no primeiro 401
  antes de forçar logout.
- **Roteamento**: `react-router 7` com `ProtectedRoute` que redireciona para `/login` quando não
  autenticado. Nenhum dado sensível em URL.
- **Deploy**: `wrangler.toml` + CI job `frontend-ci` (type-check + build). Nenhuma credencial
  comprometida no repositório; variáveis de ambiente injetadas pelo Cloudflare Pages dashboard.
- **CORS**: origem `https://*.pages.dev` e a origem do domínio personalizado são adicionadas a
  `MPLACAS_CORS_ALLOWED_ORIGINS` no Cloud Run.

## Consequências

### Positivas

- Múltiplos usuários com senhas individuais, rastreáveis por `credential_id` na trilha de auditoria
  (ADR-032).
- `organization_id` prepara o sistema para isolamento completo de dados por organização nos routers
  — fechado pelo ADR-053 (dependency `ReadPlant`/`AdminPlant`, teste-guarda estrutural).
- Frontend desacoplado permite atualizações de UI sem redeploy do backend.
- Tokens curtos (15 min) reduzem a janela de exposição; refresh token in-memory impede persistência
  de credenciais de longa duração no navegador.
- Cloudflare Pages serve o frontend globalmente via CDN sem custo adicional de compute.

### Negativas / Limites atuais

- ~~`organization_id` ainda não filtra consultas nos routers de dados~~ — fechado pelo ADR-053:
  todo router de dado valida a organização do chamador via `ReadPlant`/`AdminPlant`, com teste
  estrutural (`tests/test_plant_scope_guard.py`) impedindo regressão futura.
- Refresh token em memória: usuários precisam fazer login ao recarregar a aba — tradeoff de
  segurança intencional versus conveniência.
- `MPLACAS_JWT_SECRET` precisa ser rotacionado manualmente — rotacionar o secret invalida todos
  os access tokens em circulação de uma vez (não há revogação seletiva de access token). Refresh
  tokens já têm revogação individual via `auth_sessions` (Phase 2b).
- Não há endpoint de cadastro público nem fluxo de convite — usuários são criados via CLI admin
  ou migração.

## Próximos passos

Rastreados item a item, com evidência de código, em `docs/CHECKLIST_SAAS_MULTITENANCY.md`:

1. ~~Extrair `organization_id` do JWT e propagar como contexto de autorização nos routers de
   dados~~ — concluído, ver ADR-053.
2. Adicionar endpoint de gerenciamento de organizações (`GET/POST /organizations`).
3. Implementar fluxo de convite/ativação de usuário.

## Referências

- ADR-045: decisão single-tenant original
- ADR-051: Neon PostgreSQL como banco gerenciado
- ADR-031: chave de leitura operacional (precursor do RBAC)
- ADR-043/044: usuários nomeados e credenciais persistidas com expiração
- `infra/gcp/set-secrets.sh`: provisionamento de secrets no GCP
- `infra/gcp/lib.sh`: validação de CORS e endpoints Neon
