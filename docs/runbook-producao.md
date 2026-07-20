# Runbook de Produção — Mplacas

Guia de implantação completo: backend no Google Cloud Run e frontend no Cloudflare Pages.

> **IMPORTANTE:** Nunca ative `set -x` durante operações com segredos. O modo de depuração
> imprime todos os valores de variáveis no terminal, incluindo senhas e DSNs.

---

## 1. Pré-requisitos

### Ferramentas

| Ferramenta | Versão mínima | Onde obter |
|---|---|---|
| `gcloud` CLI | qualquer recente | Google Cloud Shell (já incluso) |
| `openssl` | qualquer | presente no Google Cloud Shell |
| Python 3.12 | 3.12+ | presente no Google Cloud Shell |
| `alembic` | qualquer | instalado no ambiente Python do projeto |
| `wrangler` (npx) | qualquer recente | via `npm` / `npx` |
| `gh` CLI | qualquer recente | GitHub CLI — para cadastrar Secrets/Variables |
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

## 2. Resetar senha do Neon

> **ATENÇÃO:** Se a URL de banco de dados já foi exposta anteriormente (ex.: digitada em
> um terminal com `set -x` ativo, registrada em logs ou incluída em algum arquivo), o
> endpoint Neon deve ser rotacionado **no painel do Neon** antes de qualquer passo abaixo.
>
> Passos no painel Neon:
> 1. Acesse o projeto no [console Neon](https://console.neon.tech).
> 2. Navegue até **Branches > main > Connection string**.
> 3. Clique em **Reset password** para gerar novas credenciais.
> 4. Copie os dois endpoints (pooled e direto) para usar nos passos 3 e 4 abaixo.

---

## 3. Cadastrar URL pooled (runtime)

O endpoint **pooled** do Neon (hostname com `-pooler`) é usado pelo Cloud Run runtime.
Ele suporta alto volume de conexões curtas.

```bash
bash infra/gcp/set-secrets.sh database-runtime
```

O script solicita o valor de forma interativa (sem eco). Nunca use `echo` ou `export`
para passar a URL — o valor não deve aparecer no histórico do shell.

---

## 4. Cadastrar URL direta (migrações)

O endpoint **direto/não-pooled** do Neon é obrigatório para migrações (`alembic upgrade
head`). DDL requer conexão direta — o endpoint pooled não é aceito para esse fim.

```bash
bash infra/gcp/set-secrets.sh database-migration
```

---

## 5. Cadastrar chave operacional

```bash
bash infra/gcp/set-secrets.sh operations-key
```

---

## 6. Gerar JWT secret (uma única vez)

```bash
bash infra/gcp/set-secrets.sh jwt
```

O script gera 32 bytes aleatórios via `openssl rand -base64 32` e os armazena diretamente
no Secret Manager — o valor nunca é impresso nem salvo em variável de shell.

Se o secret já existir (re-execução após falha parcial), o script avisa e sai sem
modificar o valor. Para rotacionar intencionalmente:

```bash
bash infra/gcp/set-secrets.sh jwt --rotate-jwt
```

A rotação exige digitação de `CONFIRMAR` e invalida todos os tokens JWT ativos.

---

## 7. Primeiro deploy do backend

Configure `infra/gcp/config.env` (ver seção 1) e execute:

```bash
bash infra/gcp/bootstrap.sh "$GCP_PROJECT_ID"
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
| `MPLACAS_DATABASE_URL` | Secret Manager (`mplacas-database-url`) | DSN pooled do Neon (runtime) |
| `MPLACAS_OPERATIONS_API_KEY` | Secret Manager (`mplacas-operations-key`) | Chave de operações |
| `MPLACAS_JWT_SECRET` | Secret Manager (`mplacas-jwt-secret`) | Segredo para assinatura de JWT |

---

## 8. Executar migrações

Após o deploy do backend, execute as migrações via Cloud Run Job. O job usa o endpoint
**direto** (`mplacas-migration-database-url`), não o pooled.

```bash
bash infra/gcp/run-migrations.sh
```

O script detecta a imagem já implantada e executa `alembic upgrade head` no ambiente
de produção, com confirmação explícita antes de rodar.

---

## 9. Confirmar usuário existente ou criar

Verifique se o usuário administrador existe no banco:

```bash
# Use a URL direta (não-pooled) para operações admin
MPLACAS_DATABASE_URL="$(
  gcloud secrets versions access latest \
    --secret=mplacas-migration-database-url \
    --project="$GCP_PROJECT_ID"
)" python3 -c "
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select, text

async def check():
    engine = create_async_engine(os.environ['MPLACAS_DATABASE_URL'])
    async with AsyncSession(engine) as s:
        rows = (await s.execute(text(\"SELECT name, active FROM operational_users\"))).all()
        for row in rows:
            print(row)
    await engine.dispose()

asyncio.run(check())
"
```

Se o usuário não existir, crie-o via API de credenciais antes de prosseguir.

---

## 10. Definir senha administrativa

> **NÃO ative `set -x` antes deste bloco.** A variável `MPLACAS_DATABASE_URL` seria
> impressa no terminal.

```bash
MPLACAS_DATABASE_URL="$(
  gcloud secrets versions access latest \
    --secret=mplacas-migration-database-url \
    --project="$GCP_PROJECT_ID"
)" python scripts/set-admin-password.py --username "$NOME_DO_USUARIO"
```

A variável existe apenas no escopo do comando — não é `export`ada nem aparece no histórico
quando o comando é digitado desta forma.

O script:
- Lê a senha de forma interativa (sem eco) ou do Secret Manager quando
  `MPLACAS_ADMIN_PASSWORD_SECRET` está definido.
- Falha se o usuário não existir, estiver inativo, ou houver duplicatas de nome.
- Nunca imprime a senha, o hash ou a URL completa.

---

## 11. Criar projeto Direct Upload no Cloudflare

O projeto Cloudflare Pages deve ser criado via **Direct Upload** (Wrangler), e não pelo
fluxo "Connect to Git" do dashboard. Isso evita dois pipelines concorrentes (Cloudflare
nativo + GitHub Actions), que podem sobrescrever deploys mutuamente.

```bash
npx wrangler pages project create mplacas-frontend --production-branch main
```

O deploy é feito exclusivamente pelo workflow `deploy-frontend.yml` (via GitHub Actions).
Não configure nenhuma integração de Git direta no painel Cloudflare para este projeto.

---

## 12. Cadastrar GitHub Secret e Variables

Configure no repositório GitHub em **Settings > Secrets and variables > Actions**:

| Nome | Tipo | Onde cadastrar | Descrição |
|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | Secret | GitHub Secrets | Token da API Cloudflare com permissão `Pages:Edit` |
| `VITE_API_URL` | Variable | GitHub Variables | URL pública do Cloud Run (ex.: `https://mplacas-api-xxx.run.app`) |
| `VITE_PLANT_ID` | Variable | GitHub Variables | UUID da planta padrão exibida no dashboard |
| `CLOUDFLARE_ACCOUNT_ID` | Variable | GitHub Variables | Account ID da conta Cloudflare |

**Importante:** `VITE_API_URL` e `VITE_PLANT_ID` são incluídos no bundle JavaScript e ficam
visíveis no navegador — não use valores secretos nessas variáveis.

---

## 13. Configurar CORS

Após o deploy do backend, atualize `MPLACAS_CORS_ALLOWED_ORIGINS` em `config.env` com
o domínio exato do Cloudflare Pages. Nunca use wildcard (`*`) quando há autenticação
com credenciais (Authorization / cookies).

Exemplo:

```text
MPLACAS_CORS_ALLOWED_ORIGINS=https://mplacas-frontend.pages.dev
```

Se o domínio personalizado for configurado posteriormente, repita os passos 14 e 15 com
o novo domínio.

---

## 14. Redeploy do backend com CORS

```bash
bash infra/gcp/deploy-service.sh
```

O script valida que `MPLACAS_CORS_ALLOWED_ORIGINS` está definido, não é wildcard e começa
com `https://` antes de executar o deploy.

---

## 15. Deploy manual do frontend

O deploy é realizado automaticamente ao fazer push para `main` quando arquivos em
`frontend/**` são alterados.

Para disparar manualmente:

1. Acesse o repositório no GitHub.
2. Vá em **Actions** > **Deploy Frontend**.
3. Clique em **Run workflow** > selecione `main` > **Run workflow**.

O workflow valida que todas as variáveis e segredos estão presentes antes de iniciar o
build. Se algum estiver ausente, ele falha imediatamente com mensagem clara.

---

## 16. Smoke tests seguros

Execute em sequência após o deploy completo de backend e frontend.

> **NÃO ative `set -x` antes deste bloco.**

```bash
# 1. Verificar saúde do backend
curl -fsS "$BACKEND_URL/health"
# Esperado: {"status":"ok"}

# 2. Verificar prontidão do backend
curl -fsS "$BACKEND_URL/ready"
# Esperado: {"status":"ready"}

# 3. Autenticar de forma segura — senha lida sem eco, nunca em argumento de linha de comando

# Leitura sem eco
read -rsp "Senha do admin: " _ADMIN_PASS
echo

# Gera o JSON sem expor a senha no histórico
_LOGIN_BODY="$(python3 -c "
import json, os
print(json.dumps({'username': '$ADMIN_USER', 'password': os.environ['_ADMIN_PASS']}))
" )"

# Envia via stdin; nunca usa -d '{"password":"..."}'
TOKEN="$(
  curl -sf -X POST "$BACKEND_URL/auth/login" \
    -H "Content-Type: application/json" \
    --data-binary @- <<< "$_LOGIN_BODY" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
)"

unset _ADMIN_PASS _LOGIN_BODY

# 4. Buscar dashboard executivo
curl -fsS "$BACKEND_URL/energy/executive/latest" \
  -H "Authorization: Bearer $TOKEN"
# Esperado: payload JSON com dados do dashboard
```

Verifique também o frontend em `https://mplacas-frontend.pages.dev` — o login deve
funcionar e carregar dados do dashboard.

---

## Referências

- `infra/gcp/deploy-service.sh` — deploy do Cloud Run
- `infra/gcp/set-secrets.sh` — gerenciamento granular de segredos (subcomandos)
- `infra/gcp/run-migrations.sh` — execução de migrações via Cloud Run Job (URL direta)
- `scripts/set-admin-password.py` — definição de senha do administrador (asyncpg)
- `.github/workflows/deploy-frontend.yml` — pipeline de deploy do frontend (Direct Upload)
- `infra/gcp/config.example.env` — template de configuração (copiar para `config.env`)
