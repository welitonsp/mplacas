# Runbook de Produção — Mplacas

> **⚠️ OBSOLETO — 2026-08-26.** Este runbook descreve a operação no Google Cloud, plataforma da
> qual o projeto saiu (ver `docs/ADR-076-saida-do-google-cloud.md`). Os scripts `infra/gcp/*` que ele
> referencia **não existem mais no repositório**. Não execute os passos daqui.
>
> Mantido apenas como memória histórica. Para a plataforma atual (Render + GitHub Actions), use
> `docs/RUNBOOK_DEPLOY.md`.

Fonte oficial para implantação do backend no Google Cloud Run, banco Neon e frontend no Cloudflare Pages.

> Nunca use `set -x` durante operações com segredos. Não cole connection strings, tokens ou senhas em mensagens, arquivos versionados ou argumentos de linha de comando.

## 1. Atualizar o repositório e preparar o Cloud Shell

```bash
cd ~
if [ ! -d "mplacas-repo/.git" ]; then
  git clone https://github.com/welitonsp/mplacas.git mplacas-repo
fi
cd ~/mplacas-repo
git switch main
git pull --ff-only origin main

python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

test -f infra/gcp/config.env || cp infra/gcp/config.example.env infra/gcp/config.env
nano infra/gcp/config.env
```

O Python deve ser 3.12 ou superior. Preencha apenas valores não sensíveis:

```text
GCP_PROJECT_ID=mplacas
GCP_REGION=us-central1
GCP_SERVICE_NAME=mplacas-api
GCP_MIGRATION_JOB_NAME=mplacas-migrate
GCP_RUNTIME_SERVICE_ACCOUNT=mplacas-runtime
GCP_MIN_INSTANCES=0
GCP_MAX_INSTANCES=1
GCP_CPU=1
GCP_MEMORY=512Mi
GCP_CONCURRENCY=20
GCP_REQUEST_TIMEOUT=60
MPLACAS_TIMEZONE=America/Sao_Paulo
MPLACAS_CORS_ALLOWED_ORIGINS=
```

Não coloque URLs do Neon ou outras credenciais em `config.env`.

## 2. Carregar a configuração e preparar o projeto GCP

```bash
source .venv/bin/activate
source infra/gcp/config.env
gcloud config set project "$GCP_PROJECT_ID"
bash infra/gcp/bootstrap.sh "$GCP_PROJECT_ID"
```

Digite o ID do projeto quando o script solicitar confirmação.

## 3. Separar e rotacionar os papéis do Neon

O backend e as migrations não podem compartilhar `neondb_owner`:

1. Use `mplacas_runtime` no endpoint pooled; o papel deve ser `NOBYPASSRLS`, sem ownership,
   criação de banco ou criação de roles, e receber somente DML/sequence no schema `public`.
2. Use `neondb_owner` somente no endpoint direto do job de migrations.
3. Rotacione senhas por canal sem eco e cadastre cada URL no secret correspondente.
4. Exija `sslmode=require&channel_binding=require` uma única vez; rejeite parâmetros duplicados,
   whitespace e qualquer URL aninhada dentro da query string.

Nunca reutilize senha ou URL antiga. Desative a versão anterior somente depois de validar
`/ready`, smoke, watchdog e o job de migração; não destrua versões no mesmo procedimento.

## 4. Cadastrar separadamente os segredos GCP

Execute cada comando e cole o valor somente no prompt sem eco:

```bash
bash infra/gcp/set-secrets.sh database-runtime
bash infra/gcp/set-secrets.sh database-migration
bash infra/gcp/set-secrets.sh operations-key
bash infra/gcp/set-secrets.sh jwt
```

| Secret Manager | Uso |
|---|---|
| `mplacas-database-url` | endpoint Neon pooled do serviço web, role `mplacas_runtime` |
| `mplacas-migration-database-url` | endpoint Neon direto do job, role `neondb_owner` |
| `mplacas-operations-api-key` | autenticação operacional do backend |
| `mplacas-jwt-secret` | assinatura dos tokens de login |

O script rejeita endpoint direto no subcomando `database-runtime` e endpoint pooled no subcomando `database-migration`.
Também rejeita credenciais ausentes, parâmetros duplicados/desconhecidos, TLS/channel binding
fracos, whitespace e connection strings concatenadas.

Não execute `jwt --rotate-jwt` durante a implantação normal. Essa opção invalida tokens ativos e exige confirmação explícita.

## 5. Criar o projeto Direct Upload no Cloudflare Pages

O frontend usa GitHub Actions com Wrangler. Não configure **Connect to Git** no painel Cloudflare.

```bash
cd ~/mplacas-repo/frontend
npm ci
npx wrangler login
npx wrangler whoami
npx wrangler pages project create mplacas-frontend --production-branch main
cd ~/mplacas-repo
```

Confirme no painel Cloudflare o domínio atribuído. O esperado é:

```text
https://mplacas-frontend.pages.dev
```

Se outro nome for necessário, pare a implantação e atualize de forma revisada o workflow e o `wrangler.toml`.

## 6. Configurar a origem CORS real

```bash
nano infra/gcp/config.env
```

Defina a origem exata, sem barra final:

```text
MPLACAS_CORS_ALLOWED_ORIGINS=https://mplacas-frontend.pages.dev
```

Depois carregue novamente:

```bash
source infra/gcp/config.env
```

A validação rejeita HTTP, wildcard, credenciais, caminhos, query strings, fragmentos, espaços e entradas vazias.

## 7. Fazer o primeiro deploy do backend

```bash
bash infra/gcp/deploy-service.sh
```

Digite a confirmação exata solicitada. O serviço usa:

- `mplacas-database-url` como `MPLACAS_DATABASE_URL`;
- `mplacas-operations-api-key` como `MPLACAS_OPERATIONS_API_KEY`;
- `mplacas-jwt-secret` como `MPLACAS_JWT_SECRET`.

## 8. Executar as migrações

```bash
bash infra/gcp/run-migrations.sh
```

O Cloud Run Job usa exclusivamente `mplacas-migration-database-url`, com conexão direta e SSL obrigatório no Neon.

## 9. Confirmar o usuário administrador

```bash
source .venv/bin/activate
read -rp "Nome exato do usuário administrador: " ADMIN_USER

MPLACAS_DATABASE_URL="$(
  gcloud secrets versions access latest \
    --secret=mplacas-migration-database-url \
    --project="$GCP_PROJECT_ID"
)" python3 scripts/set-admin-password.py \
  --username "$ADMIN_USER" \
  --check-user
```

O comando apenas confirma que o usuário existe, é único e está ativo. Caso ele não exista, interrompa a implantação e crie o usuário pelo fluxo administrativo aprovado antes de continuar.

## 10. Definir a senha do administrador

```bash
MPLACAS_DATABASE_URL="$(
  gcloud secrets versions access latest \
    --secret=mplacas-migration-database-url \
    --project="$GCP_PROJECT_ID"
)" python3 scripts/set-admin-password.py --username "$ADMIN_USER"
```

A senha é lida duas vezes sem eco, deve possuir no mínimo 12 caracteres e não aparece no histórico. A URL existe apenas no ambiente do processo e não fica exportada na sessão.

## 11. Obter a URL pública do backend

```bash
BACKEND_URL="$(
  gcloud run services describe "$GCP_SERVICE_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT_ID" \
    --format='value(status.url)'
)"
printf 'Backend: %s\n' "$BACKEND_URL"
```

A URL, sem barra final, será o valor de `VITE_API_URL`.

## 12. Obter o UUID da planta

No **SQL Editor** do Neon, execute:

```sql
SELECT id, name
FROM plants
ORDER BY created_at;
```

Copie o UUID da planta que será exibida pelo dashboard. Não invente um UUID se a consulta não retornar registros; cadastre a planta primeiro.

## 13. Cadastrar GitHub Secret e Variables

No repositório `welitonsp/mplacas`:

```text
Settings → Secrets and variables → Actions
```

Secret:

| Nome | Valor |
|---|---|
| `CLOUDFLARE_API_TOKEN` | token Cloudflare limitado a Pages:Edit |

Variables:

| Nome | Valor |
|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | Account ID mostrado pelo Wrangler/Cloudflare |
| `VITE_API_URL` | valor de `BACKEND_URL` |

As variáveis `VITE_*` ficam visíveis no bundle do navegador e nunca podem conter segredos.

## 14. Executar o deploy do frontend

No GitHub:

```text
Actions → Deploy Frontend → Run workflow → main → Run workflow
```

O workflow deve concluir:

```text
Validate required configuration
Install dependencies
Type check
Build
Deploy to Cloudflare Pages
```

## 15. Executar smoke tests sem expor a senha

```bash
curl -fsS "$BACKEND_URL/health"
curl -fsS "$BACKEND_URL/ready"

read -rsp "Senha do admin: " _ADMIN_PASS
echo

_LOGIN_BODY="$(
  printf '%s\0%s' "$ADMIN_USER" "$_ADMIN_PASS" |
    python3 -c 'import json,sys; raw=sys.stdin.buffer.read(); user,password=raw.split(b"\0",1); print(json.dumps({"username":user.decode(),"password":password.decode()}))'
)"
unset _ADMIN_PASS

TOKEN="$(
  printf '%s' "$_LOGIN_BODY" |
    curl -fsS -X POST "$BACKEND_URL/auth/login" \
      -H "Content-Type: application/json" \
      --data-binary @- |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
)"
unset _LOGIN_BODY

curl -fsS "$BACKEND_URL/energy/executive/latest" \
  -H "Authorization: Bearer $TOKEN"

unset TOKEN
```

Depois abra:

```text
https://mplacas-frontend.pages.dev
```

Confirme login, carregamento do dashboard e ausência de erros de CORS.

## 16. Verificar implantação e custos

```bash
bash infra/gcp/verify-deployment.sh
bash infra/gcp/audit-costs.sh
```

Confirme:

- `/health` e `/ready` aprovados;
- migração concluída;
- uma versão `ENABLED` para cada secret gerenciado;
- Cloud Run com mínimo 0 e máximo 1 instância;
- nenhum segredo em logs, commits ou capturas;
- orçamento e alertas de custo ativos.

## 17. Automatizar `audit-costs.sh` (Cloud Scheduler + Cloud Run Job)

Além da execução manual acima, o guardrail roda automaticamente todo dia às `04:00`
(`MPLACAS_TIMEZONE`) através de um Cloud Run Job dedicado (`mplacas-cost-audit`) disparado por
Cloud Scheduler, sob uma identidade só-leitura (`mplacas-auditor`) que nunca recebe
`roles/secretmanager.secretAccessor` nem `roles/billing.viewer` (esse último está fora do escopo
do projeto; o job pula esse check específico via `MPLACAS_AUDIT_SKIP_BILLING=1`, mantendo todas as
outras verificações ativas). Provisionar/atualizar com:

```bash
bash infra/gcp/provision-cost-audit.sh
```

Este script constrói a imagem a partir de `infra/gcp/Dockerfile.audit` (não a imagem principal da
aplicação — não contém código-fonte nem segredos), cria/atualiza a service account
`mplacas-auditor`, o Cloud Run Job `mplacas-cost-audit` e o schedule diário. É idempotente e exige
confirmação explícita (`PROVISION-COST-AUDIT-<project-id>`).

### Achado corrigido nesta automação: falso-positivo no allowlist do Cloud Scheduler

Antes desta automação, `audit-costs.sh` falhava (`fail_if_output`) para **qualquer** Cloud
Scheduler job com nome `~mplacas` — incluindo os 8 schedulers legítimos já criados por
`infra/gcp/provision-operations.sh` (`mplacas-collect`, `mplacas-daily-pipeline`, etc.). Rodar o
guardrail em modo agendado teria disparado alerta de "recurso proibido" a cada execução, contra a
própria infraestrutura operacional do projeto. Corrigido trocando a regra "qualquer scheduler
`~mplacas` falha" por uma allowlist (`MPLACAS_EXPECTED_SCHEDULER_JOBS` em `infra/gcp/lib.sh`, fonte
única de verdade também consultada por `provision-operations.sh` e `provision-cost-audit.sh`): só
falha um scheduler `~mplacas` que **não** esteja nessa lista conhecida.

### Como responder ao alerta `Mplacas - falha em Cloud Run Job operacional`

O job `mplacas-cost-audit` está incluído na mesma política de monitoramento usada pelos demais
jobs operacionais (`infra/gcp/monitoring/operational-job-failure.json`). Se o alerta disparar com
`resource.labels.job_name="mplacas-cost-audit"`:

1. Abra os logs da execução mais recente do job no Cloud Run.
2. Se a falha for `prohibited resource detected: ...`, há um recurso `~mplacas` real fora do
   allowlist (Cloud SQL, Compute Engine, Load Balancer, VPC Connector ou Cloud Scheduler não
   provisionado por `provision-operations.sh`/`provision-cost-audit.sh`) — investigue e remova o
   recurso, ou, se for legítimo e esperado, adicione-o a `MPLACAS_EXPECTED_SCHEDULER_JOBS` (ou
   ajuste o guardrail correspondente) em um PR revisado.
3. Se a falha for de permissão (`PERMISSION_DENIED`), confirme que `mplacas-auditor` ainda possui
   os papéis listados em `infra/gcp/provision-cost-audit.sh` (`AUDITOR_ROLES`) — nunca conceda
   `roles/secretmanager.secretAccessor` ou `roles/billing.viewer` a essa identidade.
4. Depois de corrigir, rode `bash infra/gcp/audit-costs.sh` manualmente (com `MPLACAS_CONFIG_FROM_ENV`
   não setado, usando `config.env` local) para confirmar que o guardrail passa antes de aguardar a
   próxima execução agendada.

## Atualizações futuras

```bash
cd ~/mplacas-repo
git switch main
git pull --ff-only origin main
source .venv/bin/activate
source infra/gcp/config.env
bash infra/gcp/deploy-service.sh
bash infra/gcp/run-migrations.sh
bash infra/gcp/verify-deployment.sh
bash infra/gcp/audit-costs.sh
```

Execute migrações somente depois de revisar as alterações de schema da versão.
