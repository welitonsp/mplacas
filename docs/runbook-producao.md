# Runbook de Produção — Mplacas

Guia de implantação completo: backend no Google Cloud Run e frontend no Cloudflare Pages.

---

## 1. Pré-requisitos

### Ferramentas

| Ferramenta | Versão mínima | Onde obter |
|---|---|---|
| `gcloud` CLI | qualquer recente | Google Cloud Shell (já incluso) |
| `openssl` | qualquer | presente no Google Cloud Shell |
| Python 3.12 | 3.12+ | presente no Google Cloud Shell |
| Node.js | 22 | não necessário localmente — usado pelo GitHub Actions |

### Permissões GCP

O operador precisa, no projeto GCP alvo:
- `roles/run.admin`
- `roles/secretmanager.admin`
- `roles/iam.serviceAccountAdmin`
- `roles/billing.viewer`

### Variáveis de shell necessárias

Defina em `infra/gcp/config.env` (nunca no Git):

```text
GCP_PROJECT_ID=<id-do-projeto>
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
MPLACAS_CORS_ALLOWED_ORIGINS=<url-exata-do-pages>
```

Jamais use valores reais de segredos em `config.env`.

---

## 2. Neon e migrações

Use o endpoint **não-pooled** do Neon para migrações (DDL requer conexão direta):

```bash
export MPLACAS_DATABASE_URL="$NON_POOLED_DSN"
alembic upgrade head
```

Após o deploy do Cloud Run, execute a migração via job gerenciado:

```bash
bash infra/gcp/run-migrations.sh
```

O job usa uma conexão direta ao banco; confirme que `MPLACAS_DATABASE_URL` no Secret Manager aponta para o endpoint não-pooled do Neon.

---

## 3. JWT secret

Execute em terminal interativo no Google Cloud Shell:

```bash
bash infra/gcp/set-secrets.sh
```

O script:
- Gera 32 bytes aleatórios com `openssl rand -base64 32`.
- Armazena o valor diretamente no Secret Manager como `mplacas-jwt-secret` via pipe — o valor nunca é impresso nem salvo em variável de shell.
- Concede acesso exclusivo à service account de runtime.
- Desabilita versões anteriores do segredo.

O script também rotaciona `mplacas-database-url` e `mplacas-operations-api-key` na mesma execução.

---

## 4. Usuário administrador e senha

Após o banco estar migrado e acessível:

```bash
export MPLACAS_DATABASE_URL="postgresql+psycopg2://$NON_POOLED_DSN_NO_SCHEME"
python scripts/set-admin-password.py --username $NOME_DO_USUARIO
```

O script lê a senha de forma interativa (sem eco) ou do Secret Manager quando `MPLACAS_ADMIN_PASSWORD_SECRET` está definido. A senha nunca aparece em argumentos de linha de comando, logs ou output.

Pré-requisitos:
- O usuário com `name == $NOME_DO_USUARIO` e `active == true` deve já existir no banco (criado via API de credenciais).
- `MPLACAS_DATABASE_URL` deve apontar para endpoint sincronizado com `psycopg2`.

---

## 5. Deploy do backend

Configure `infra/gcp/config.env` (ver seção 1) e execute:

```bash
bash infra/gcp/bootstrap.sh "$GCP_PROJECT_ID"
bash infra/gcp/set-secrets.sh
bash infra/gcp/deploy-service.sh
```

Variáveis obrigatórias injetadas no Cloud Run (nunca use valores reais aqui — apenas nomes):

| Variável de ambiente | Fonte | Descrição |
|---|---|---|
| `MPLACAS_ENVIRONMENT` | `--set-env-vars` | Deve ser `production` |
| `MPLACAS_TIMEZONE` | `--set-env-vars` | Fuso-horário (`America/Sao_Paulo`) |
| `MPLACAS_GCP_PROJECT_ID` | `--set-env-vars` | ID do projeto GCP |
| `MPLACAS_CLOUD_TRACE_ENABLED` | `--set-env-vars` | `true` em produção |
| `MPLACAS_CLOUD_METRICS_ENABLED` | `--set-env-vars` | `true` em produção |
| `MPLACAS_CORS_ALLOWED_ORIGINS` | `--set-env-vars` | URL exata do Pages (sem wildcard) |
| `MPLACAS_DATABASE_URL` | Secret Manager | DSN do Neon (pooled para runtime) |
| `MPLACAS_OPERATIONS_API_KEY` | Secret Manager | Chave de operações |
| `MPLACAS_JWT_SECRET` | Secret Manager | Segredo para assinatura de JWT |

---

## 6. Criação do projeto Cloudflare Pages

### Via Dashboard

1. Acesse <https://dash.cloudflare.com> > **Pages**.
2. Clique em **Create a project** > **Connect to Git**.
3. Selecione o repositório `mplacas`.
4. Nome do projeto: `mplacas-frontend` (exatamente este nome).
5. Branch de produção: `main`.
6. Framework preset: **None** (o build é feito pelo GitHub Actions, não pelo Pages).

### Via Wrangler (alternativo)

```bash
npx wrangler pages project create mplacas-frontend
```

---

## 7. GitHub Secrets e Variables

Configure no repositório GitHub em **Settings > Secrets and variables > Actions**:

| Nome | Tipo | Onde cadastrar | Descrição |
|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | Secret | GitHub Secrets | Token da API Cloudflare com permissão `Pages:Edit` |
| `VITE_API_URL` | Variable | GitHub Variables | URL pública do Cloud Run (ex.: `https://mplacas-api-xxx.run.app`) |
| `VITE_PLANT_ID` | Variable | GitHub Variables | UUID da planta padrão exibida no dashboard |
| `CLOUDFLARE_ACCOUNT_ID` | Variable | GitHub Variables | Account ID da conta Cloudflare |

**Importante:** `VITE_API_URL` e `VITE_PLANT_ID` são incluídos no bundle JavaScript e ficam visíveis no navegador — não use valores secretos nessas variáveis.

---

## 8. CORS

Após o deploy do backend, atualize `MPLACAS_CORS_ALLOWED_ORIGINS` no Cloud Run com o domínio exato do Pages:

```bash
# Obtenha a URL atribuída pelo Cloudflare Pages após o primeiro deploy.
# Exemplo: https://mplacas-frontend.pages.dev
# NUNCA use wildcard (*) quando há autenticação com credenciais (Authorization / cookies).
gcloud run services update "$GCP_SERVICE_NAME" \
  --update-env-vars "MPLACAS_CORS_ALLOWED_ORIGINS=https://mplacas-frontend.pages.dev" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT_ID"
```

Se o domínio personalizado for configurado posteriormente, repita este passo com o novo domínio.

---

## 9. Deploy do frontend

O deploy é realizado automaticamente ao fazer push para `main` quando arquivos em `frontend/**` são alterados.

Para disparar manualmente:

1. Acesse o repositório no GitHub.
2. Vá em **Actions** > **Deploy Frontend**.
3. Clique em **Run workflow** > selecione `main` > **Run workflow**.

O workflow valida que todas as variáveis e segredos estão presentes antes de iniciar o build. Se algum estiver ausente, ele falha imediatamente com mensagem clara.

---

## 10. Smoke test

Execute em sequência após o deploy completo de backend e frontend:

```bash
# 1. Verificar saúde do backend
curl -fsS "$BACKEND_URL/health"
# Esperado: {"status":"ok"}

# 2. Verificar prontidão do backend
curl -fsS "$BACKEND_URL/ready"
# Esperado: {"status":"ready"}

# 3. Autenticar
TOKEN=$(curl -fsS -X POST "$BACKEND_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"'"$NOME_DO_USUARIO"'","password":"<SENHA>"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 4. Buscar dashboard executivo
curl -fsS "$BACKEND_URL/energy/executive/latest" \
  -H "Authorization: Bearer $TOKEN"
# Esperado: payload JSON com dados do dashboard
```

Verifique também o frontend em `https://mplacas-frontend.pages.dev` — o login deve funcionar e carregar dados do dashboard.

---

## Referências

- `infra/gcp/deploy-service.sh` — deploy do Cloud Run
- `infra/gcp/set-secrets.sh` — gerenciamento de segredos (inclui JWT)
- `infra/gcp/run-migrations.sh` — execução de migrações via Cloud Run Job
- `scripts/set-admin-password.py` — definição de senha do administrador
- `.github/workflows/deploy-frontend.yml` — pipeline de deploy do frontend
- `docs/RUNBOOK_GOOGLE_CLOUD_DEPLOYMENT.md` — runbook detalhado do backend GCP
