# Runbook de backup e restauração

Este runbook define o contrato mínimo para backup e teste de restauração do banco de dados do Mplacas em produção.

## Objetivos operacionais e responsabilidade

- **RPO:** no máximo 24 horas, sustentado por snapshot lógico diário e PITR do Neon habilitado.
- **RTO:** até 4 horas para restaurar, validar e promover um ambiente recuperado.
- **Retenção:** 35 dias para os snapshots lógicos criptografados e seus manifests; a janela de
  PITR deve ser conferida mensalmente no plano Neon contratado.
- **Owner:** responsável definido na variável protegida `MPLACAS_RESTORE_DRILL_OWNER`.
- **Alerta:** falha do workflow abre ou atualiza a issue `[P1-06] Restore drill failure`.

PITR e snapshot lógico são controles complementares. A existência do recurso de PITR no provedor
não substitui o restore drill, e um dump sem restauração comprovada não atende este contrato.

## Objetivo

Garantir que dados energéticos, financeiros, faturas, auditoria, sessões operacionais e históricos possam ser recuperados de forma verificável após falha operacional, perda acidental ou incidente de infraestrutura.

## Escopo

Este runbook cobre bancos PostgreSQL usados por `MPLACAS_DATABASE_URL`. SQLite é permitido apenas para desenvolvimento e testes locais; não deve ser tratado como banco de produção.

## Princípios obrigatórios

- Backups nunca devem ser gravados no repositório Git.
- Backups devem ser armazenados em local privado, criptografado e com acesso mínimo necessário.
- Nenhum backup deve ser validado apenas pela existência do arquivo: restauração de ensaio é obrigatória.
- Teste de restauração deve usar banco descartável, isolado do banco de produção.
- Antes de qualquer restauração sobre ambiente real, a aplicação deve ser colocada em modo operacional controlado e a janela deve ser comunicada.

## Variáveis esperadas

```bash
export MPLACAS_DATABASE_URL="postgresql://user:password@host:5432/mplacas"
export MPLACAS_RESTORE_DATABASE_URL="postgresql://user:password@host:5432/mplacas_restore_check"
export BACKUP_DIR="./private-backups"
```

`MPLACAS_DATABASE_URL` aponta para a origem. `MPLACAS_RESTORE_DATABASE_URL` aponta para um banco descartável usado somente para validação de restauração.

Na automação, configure o environment `production-restore-drill` com:

- secrets `MPLACAS_BACKUP_SOURCE_URL` e `MPLACAS_BACKUP_ENCRYPTION_PASSPHRASE`;
- variável `MPLACAS_RESTORE_DRILL_OWNER`;
- acesso administrativo restrito para alterações manuais de secrets.

O workflow cria um PostgreSQL 18 efêmero dentro do runner e fixa
`MPLACAS_RESTORE_DATABASE_URL=postgresql://postgres@localhost:5432/mplacas_restore_check` e
`MPLACAS_RESTORE_CONFIRM_HOST=localhost`; o serviço é destruído com o runner. O hostname de
confirmação deve ser exatamente o hostname do alvo descartável e diferente do hostname de produção.
Essa validação fail-closed acontece antes do `pg_restore`. Execuções locais podem usar uma branch
Neon descartável, mas o workflow não depende de infraestrutura externa para o destino.

## Automação diária

O workflow `.github/workflows/restore-drill.yml` executa diariamente:

```bash
bash infra/backup/run-restore-drill.sh
```

Ele cria um PostgreSQL 18 efêmero no runner e valida que o cliente `pg_dump` também está na
versão principal 18 antes de gerar um dump custom da origem e validar sua estrutura,
calcula SHA-256, persiste somente a cópia cifrada com GPG/AES-256 por 35 dias, restaura no alvo
descartável, aplica `alembic upgrade head`, verifica
tabelas críticas e inicia uma API isolada para validar `/ready`. O artifact contém o dump cifrado
e um manifest JSON auditável; o dump em claro é eliminado ao final mesmo em caso de falha.
A origem é validada e normalizada de `postgres://` ou `postgresql+asyncpg://` para a DSN libpq
`postgresql://`, sem registrar credenciais, e é fornecida explicitamente a `pg_dump --dbname`.
Isso impede fallback silencioso para o socket PostgreSQL local quando o backup deve ler a origem.

## Backup lógico

Crie o diretório privado de destino:

```bash
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
```

Gere o backup no formato custom do PostgreSQL:

```bash
backup_file="$BACKUP_DIR/mplacas-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner --no-acl --file "$backup_file" "$MPLACAS_DATABASE_URL"
sha256sum "$backup_file" > "$backup_file.sha256"
```

Critérios mínimos:

- `pg_dump` termina com exit code zero.
- Arquivo `.dump` existe e tem tamanho maior que zero.
- Arquivo `.sha256` é gerado junto ao dump.
- O backup é movido para armazenamento privado fora do repositório.

## Restauração de ensaio

A restauração de ensaio deve ser executada em banco descartável:

```bash
createdb "$MPLACAS_RESTORE_DATABASE_URL" || true
pg_restore --clean --if-exists --no-owner --no-acl --dbname "$MPLACAS_RESTORE_DATABASE_URL" "$backup_file"
```

Em seguida, rode checagens mínimas de integridade:

```bash
psql "$MPLACAS_RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
SELECT COUNT(*) >= 0 AS plants_table_readable FROM plants;
SELECT COUNT(*) >= 0 AS users_table_readable FROM operational_users;
SELECT COUNT(*) >= 0 AS credentials_table_readable FROM api_credentials;
SELECT COUNT(*) >= 0 AS migrations_table_readable FROM alembic_version;
SQL
```

Critérios mínimos:

- `pg_restore` termina com exit code zero.
- As tabelas críticas são consultáveis.
- `alembic_version` está presente no banco restaurado.
- O teste não usa o banco de produção como destino.

## Teste de aplicação contra banco restaurado

Após a restauração de ensaio, execute uma instância isolada da API apontando para o banco restaurado:

```bash
MPLACAS_ENVIRONMENT=production \
MPLACAS_DATABASE_URL="$MPLACAS_RESTORE_DATABASE_URL" \
MPLACAS_JWT_SECRET="restore-check-only" \
MPLACAS_OPERATIONS_API_KEY="restore-check-only" \
python -m mplacas.cloud_run
```

Em outro terminal, valide:

```bash
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8080/ready
```

Critérios mínimos:

- `/health` retorna sucesso.
- `/ready` retorna sucesso somente com banco restaurado acessível e JWT configurado em produção.
- Falha de `/ready` bloqueia promoção do backup como restaurável.

## Frequência mínima

- Backup: diariamente enquanto houver uso real do sistema.
- Restauração de ensaio: semanalmente ou antes de qualquer mudança estrutural de banco.
- Teste extraordinário: após incidentes, migrações críticas ou alteração de infraestrutura.

## Registro operacional

Cada execução deve registrar fora do repositório:

- data e horário UTC;
- responsável;
- origem do backup;
- hash SHA-256;
- destino da restauração de ensaio;
- resultado de `pg_restore`;
- resultado de `/ready` contra o banco restaurado;
- decisão final: aprovado, reprovado ou inconclusivo.

## Condição de aceite

A pendência de backup e restauração só pode ser considerada resolvida quando existir, no mínimo, um backup recente com restauração de ensaio aprovada e registro operacional correspondente.
