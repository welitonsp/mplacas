# Runbook — integração PostgreSQL e migrations

## Objetivo

Validar o schema criado exclusivamente por Alembic e os contratos que SQLite não reproduz: locks de
linha, `FOR UPDATE SKIP LOCKED`, concorrência de refresh token, filas, outbox, RLS e `/ready` real.

## Execução canônica

O job `postgres-integration` em `.github/workflows/ci.yml` sobe um PostgreSQL descartável vazio,
instala os locks reproduzíveis e executa, nesta ordem:

```bash
alembic upgrade head
alembic check
pytest -q -m postgres_integration \
  -W 'error::pytest.PytestUnhandledThreadExceptionWarning'
```

O log é publicado como artifact `postgres-integration-report`, com retenção de 30 dias.

## Contratos cobertos

- exatamente uma rotação concorrente do refresh token vence e replay revoga a família;
- RLS falha fechada sem tenant e bypass exige role explícita;
- segundo worker de coleta não bloqueia nem captura linha já travada pelo primeiro;
- segundo worker de outbox não bloqueia nem captura evento já travado pelo primeiro;
- `alembic_version` corresponde ao head esperado;
- tabelas críticas existem após migrations, sem `Base.metadata.create_all`;
- `/ready` responde `ready` usando o PostgreSQL migrado.

## Execução local segura

Defina `MPLACAS_TEST_POSTGRES_URL` somente para um banco descartável dedicado. O teste cria registros
com UUIDs aleatórios e os remove, mas o banco deve continuar sendo de integração, nunca produção.

```powershell
$env:MPLACAS_TEST_POSTGRES_URL = 'postgresql+asyncpg://USER:PASSWORD@localhost:5432/mplacas_test'
$env:MPLACAS_DATABASE_URL = $env:MPLACAS_TEST_POSTGRES_URL
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic check
.venv\Scripts\python.exe -m pytest -q -m postgres_integration
```

Sem a variável, os testes PostgreSQL retornam `skipped` explicitamente. Não apontar a variável para um
banco desconhecido apenas para eliminar o skip.

## Evidência para fechar P1-04

Anexar ao checklist a URL da execução do workflow e o nome/ID do artifact, sem credenciais. Confirmar
que migrations, `alembic check`, refresh concorrente, RLS, fila, outbox e readiness passaram na mesma
execução. Falha em qualquer etapa mantém o item parcial.
