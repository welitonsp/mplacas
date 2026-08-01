---
name: alembic-migrations
description: Use SEMPRE que um modelo SQLAlchemy em src/mplacas/**/models.py (ou equivalente) for criado, alterado ou removido. Define o processo obrigatório para gerar, revisar e testar a migration Alembic correspondente — incluindo a convenção de revision id do projeto, que diverge do padrão default do Alembic.
---

# Migrations Alembic — Mplacas

## Regra crítica

Sempre que um agente alterar um modelo SQLAlchemy (`Column`, `Table`, `ForeignKey`,
índice, constraint), ele **MUST** gerar a migration correspondente antes de considerar
a tarefa concluída. Uma mudança de schema sem migration **NEVER** deve ser reportada
como pronta.

## Convenção de nomeação (verificada em `migrations/versions/`, diverge do default Alembic)

O projeto **não** usa o hash hexadecimal default do Alembic como revision id. Os
arquivos seguem `YYYYMMDD_NNNN_descricao_curta.py`, com `revision`/`down_revision`
casando com esse mesmo id (ver `20260720_0023_add_user_password_hash.py` como
exemplo). `alembic.ini` não tem `file_template` customizado — a convenção é aplicada à
mão após a geração. Ao criar uma migration nova:

```bash
alembic revision --autogenerate -m "descrição curta" --rev-id $(date +%Y%m%d)_NNNN
```

Onde `NNNN` é o próximo número sequencial de 4 dígitos (**MUST** checar
`migrations/versions/` para o maior número já usado — a sequência é contínua entre
datas, não reinicia por dia). Ajuste `down_revision` manualmente se o autogenerate não
detectar corretamente a revision anterior (ele deve apontar para o `revision` da última
migration na pasta, em ordem de aplicação, não necessariamente a última por nome de
arquivo).

## Passos obrigatórios

1. Altere o modelo SQLAlchemy.
2. Rode `alembic revision --autogenerate -m "..." --rev-id <YYYYMMDD_NNNN>`.
3. **CRITICAL — inspecione visualmente o arquivo gerado antes de aplicar.** O
   autogenerate do Alembic é conhecido por falsos positivos: detectar mudança de tipo
   que não existe (ex: `Numeric(10,2)` vs `Numeric(10, 2)`), recriar índices já
   existentes, ou não detectar renomeação de coluna (gera `drop` + `add` em vez de
   `alter_column`, perdendo dados). O agente **NEVER** aplica uma migration
   autogenerada sem ler o diff completo primeiro.
4. Use `with op.batch_alter_table(...)` para qualquer `ALTER` em coluna existente — o
   projeto roda SQLite em desenvolvimento (`sqlite+aiosqlite`) e SQLite não suporta
   `ALTER COLUMN` fora de batch mode. Migrations sem batch mode que só funcionam em
   Postgres vão quebrar `pytest` localmente.
5. Se a mudança introduz uma coluna `NOT NULL` em uma tabela com dados existentes,
   **não** faça isso em uma única migration. O padrão já estabelecido no projeto (ver
   `20260720_0020/0021/0022`, RBAC de organizações) é em três passos:
   1. migration A: adiciona a coluna nullable;
   2. migration B: faz backfill dos dados existentes (com regra de negócio explícita
      para casos ambíguos — falhar com mensagem operacional clara, nunca adivinhar);
   3. migration C: altera para `NOT NULL` depois que o backfill já rodou em produção.
6. Escreva `downgrade()` sempre — mesmo que seja apenas o inverso mecânico do
   `upgrade()`. Nenhuma migration do projeto está sem `downgrade()`.
7. Teste a migration:
   ```bash
   alembic upgrade head
   alembic downgrade -1
   alembic upgrade head
   ```
   Isso confirma que upgrade e downgrade são simétricos e não deixam o schema em
   estado quebrado.
8. Rode a suíte de testes relacionada (ver skill `python-quality`) — o projeto tem
   testes de contrato de migration (upgrade/downgrade) para mudanças de schema
   sensíveis (ex: `ADR-050`, campo `generation_cycle_kwh`). Se o modelo alterado tem
   teste de contrato equivalente, siga o mesmo padrão para o campo novo.

## O que NÃO fazer

- Não aplique uma migration autogenerada sem ler o arquivo primeiro.
- Não escreva uma migration que quebra em SQLite (dev) mesmo que funcione em Postgres
  (produção) — os dois motores rodam nos testes.
- Não junte "adicionar coluna NOT NULL" em uma tabela com dados em uma única migration.
- Não esqueça `downgrade()`.
