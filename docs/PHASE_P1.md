# Fase P1 — Persistência e operação

Objetivo: transformar a fundação P0 em uma plataforma capaz de preservar histórico energético próprio, de forma idempotente e auditável.

## Escopo

- PostgreSQL assíncrono com SQLAlchemy 2;
- modelos de usina, dispositivo, produção diária e versões;
- migrações Alembic;
- gravação idempotente por usina/dispositivo/data;
- preservação de alterações retroativas;
- preparação para scheduler D+1 e backfill semanal;
- health check de banco;
- testes unitários do repositório.

## Princípios

- nenhuma leitura ausente será convertida em zero;
- o valor atual do dia é provisório;
- alterações da NEPViewer geram nova versão, não sobrescrita silenciosa;
- energia usa `Decimal`, nunca `float`;
- timestamps são armazenados em UTC;
- a data de produção respeita o fuso da usina.
