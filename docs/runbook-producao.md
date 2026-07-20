# Runbook de Produção — Mplacas

Fonte oficial para implantação do backend no Google Cloud Run, banco Neon e frontend no Cloudflare Pages.

> Nunca use `set -x` durante operações com segredos. Não cole connection strings, tokens ou senhas em mensagens, arquivos versionados ou argumentos de linha de comando.

## 1. Atualizar o repositório e criar a configuração local

No Google Cloud Shell:

```bash
cd ~
if [ ! -d "mplacas-repo/.git" ]; then
  git clone https://github.com/welitonsp/mplacas.git mplacas-repo
fi
cd ~/mplacas-repo
git switch main
git pull --ff-only origin main

test -f infra/gcp/config.env || cp infra/gcp/config.example.env infra/gcp/config.env
nano infra/gcp/config.env
```

Preencha apenas valores não sensíveis:

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
source infra/gcp/config.env
gcloud config set project "$GCP_PROJECT_ID"
bash infra/gcp/bootstrap.sh "$GCP_PROJECT_ID"
```

Digite o ID do projeto quando o script solicitar confirmação.

## 3. Rotacionar a senha do Neon exposta anteriormente

No painel do Neon:

1. Abra o projeto Mplacas.
2. Selecione o role `neondb_owner`.
3. Execute **Reset password**.
4. Copie novamente as duas connection strings:
   - pooled: hostname contém `-pooler`;
   - direta: hostname não contém `-pooler`.

Nunca reutilize a senha ou as URLs antigas.

## 4. Cadastrar separadamente os segredos GCP

Execute cada comando e cole o valor somente no prompt sem eco:

```bash
bash infra/gcp/set-secrets.sh database-runtime
bash infra/gcp/set-secrets.sh database-migration
bash infra/gcp/set-secrets.sh operations-key
bash infra/gcp/set-secrets.sh jwt
```

Mapeamento:

| Secret Manager | Uso |
|---|---|
| `mplacas-database-url` | endpoint Neon pooled do serviço web |
| `mplacas-migration-database-url` | endpoint Neon direto do job de migração |
| `mplacas-operations-api-key` | autenticação operacional do backend |
| `mplacas-jwt-secret` | assinatura dos tokens de login |

O script rejeita endpoint direto no subcomando `database-runtime` e endpoint pooled no subcomando `database-migration`.

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

Se outro nome for necessário, pare a implantação e atualize de forma revisada o workflow e o `wrangler.toml`; não prossiga com nomes divergentes.

## 6. Configurar a origem CORS real

Edite:

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
| `VITE_PLANT_ID` | UUID real da planta |

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

Depois abra no navegador:

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

## Atualizações futuras

```bash
cd ~/mplacas-repo
git switch main
git pull --ff-only origin main
source infra/gcp/config.env
bash infra/gcp/deploy-service.sh
bash infra/gcp/run-migrations.sh
bash infra/gcp/verify-deployment.sh
bash infra/gcp/audit-costs.sh
```

Execute migrações somente depois de revisar as alterações de schema da versão.
