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

### Normalização de URL

A URL fornecida pelo Neon começa com `postgres://` ou `postgresql://`. asyncpg exige o scheme `postgresql+asyncpg://`. A normalização é feita em `Settings._normalize_database_url` (field_validator) de forma transparente ao operador.

## Alternativas consideradas

- **Supabase**: Similar ao Neon, mas sem database branching. Descartado.
- **Cloud SQL (GCP)**: ~$7/mês mínimo, sem free tier. Descartado para fase inicial.
- **Fly.io Postgres**: Requer VM dedicada, fora do ecossistema GCP. Descartado.

## Consequências

- A URL do banco vai para Secret Manager como `mplacas-database-url` (já configurado em `set-secrets.sh`).
- Migrações Alembic executadas pelo Cloud Run Job existente — sem mudança no fluxo de deploy.
- Branches Neon substituem ambientes de staging completos: `neon branch create --parent main`.
- Em desenvolvimento local, SQLite continua sendo o padrão (`.env.example`).
