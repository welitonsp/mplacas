# ADR-051 — Neon PostgreSQL como banco de dados de produção

**Data:** 2026-07-20  
**Status:** Aceito

## Contexto

O Mplacas roda em Cloud Run (GCP) com SQLite local no desenvolvimento. A evolução para SaaS multitenancy (ver ADR-052 planejado) exige um banco PostgreSQL com conexões remotas gerenciadas, migrações online e suporte a múltiplos ambientes (produção, staging via branch).

## Decisão

Adotar **Neon** (neon.tech) como provedor PostgreSQL gerenciado para produção e staging.

### Motivações

| Critério | Neon |
|---|---|
| Custo inicial | Free tier: 0.5 GB storage, 1 projeto |
| Staging isolado | Database branching nativo (cópia instantânea da produção) |
| Serverless scale | Escala para zero — sem custo de instância ociosa |
| asyncpg | Compatível; requer SSL via `connect_args` |
| Pooling | Pooler de conexões embutido (endpoint `:5432` pooled) |

### Configuração de conexão

asyncpg não aceita `sslmode` na URL. SSL é passado por `connect_args`:

```python
connect_args = {"ssl": "require"}   # ativado quando "neon.tech" in url
```

Pool conservador para o free tier (máx 5 conexões simultâneas por branch):

```python
pool_size=3, max_overflow=2   # pico: 5 conexões
```

### Separação de papéis

- `mplacas_runtime` usa exclusivamente o endpoint pooled e possui somente login, conexão, uso do
  schema, DML nas tabelas e uso das sequences. O papel é `NOSUPERUSER`, `NOCREATEDB`,
  `NOCREATEROLE`, `NOINHERIT` e `NOBYPASSRLS`.
- `neondb_owner` usa exclusivamente o endpoint direto no job de migrations e não é credencial da
  aplicação web.
- O runtime aplica `statement_timeout=30s`, `lock_timeout=5s` e
  `idle_in_transaction_session_timeout=60s` no nível da role.
- Novas tabelas/sequences criadas por `neondb_owner` recebem os grants runtime por default
  privileges. Isso prepara, mas não ativa, o rollout RLS definido na ADR-056.

### Normalização de URL

A URL fornecida pelo Neon começa com `postgres://` ou `postgresql://`. asyncpg exige o scheme `postgresql+asyncpg://`. A normalização é feita em `Settings._normalize_database_url` (field_validator) de forma transparente ao operador.

## Alternativas consideradas

- **Supabase**: Similar ao Neon, mas sem database branching. Descartado.
- **Cloud SQL (GCP)**: ~$7/mês mínimo, sem free tier. Descartado para fase inicial.
- **Fly.io Postgres**: Requer VM dedicada, fora do ecossistema GCP. Descartado.

## Consequências

- A URL pooled de `mplacas_runtime` vai para `mplacas-database-url`; a URL direta de
  `neondb_owner` vai para `mplacas-migration-database-url`.
- Migrações Alembic executadas pelo Cloud Run Job existente — sem mudança no fluxo de deploy.
- Branches Neon substituem ambientes de staging completos: `neon branch create --parent main`.
- Em desenvolvimento local, SQLite continua sendo o padrão (`.env.example`).
