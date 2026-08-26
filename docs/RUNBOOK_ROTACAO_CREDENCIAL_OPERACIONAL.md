# Runbook — rotação da credencial operacional

> **⚠️ OBSOLETO — 2026-08-26.** Este runbook descreve a operação no Google Cloud, plataforma da
> qual o projeto saiu (ver `docs/ADR-076-saida-do-google-cloud.md`). Os scripts `infra/gcp/*` que ele
> referencia **não existem mais no repositório**. Não execute os passos daqui.
>
> Mantido apenas como memória histórica. Para a plataforma atual (Render + GitHub Actions), use
> `docs/RUNBOOK_DEPLOY.md`. Não reative o Google Cloud para executar este procedimento antigo.

## Objetivo

Rotacionar `MPLACAS_OPERATIONS_API_KEY` sem imprimir o segredo, com validação dos consumidores e
rollback por versão do Secret Manager. Este procedimento deve ser executado depois que a versão
sem o dashboard legado estiver implantada.

## Evidência de preflight em 2026-08-01

- Projeto ativo: `mplacas`.
- Serviço: `mplacas-api`, região `us-central1`.
- Requisições Cloud Run contendo `/dashboard` nos 90 dias anteriores: zero.
- O segredo `mplacas-operations-api-key` possuía uma versão habilitada, criada em 2026-07-21.
- Nenhum valor de segredo foi consultado ou registrado durante o preflight.

Zero acessos ao dashboard reduz o risco da exposição, mas não prova que scripts administrativos
deixaram de usar a chave. Confirmar os consumidores antes da mudança.

## Checklist de consumidores

- Cloud Run API e Cloud Run Jobs.
- Scripts de operação manuais.
- Monitores externos e automações que chamam `/operations/*`.
- Integrações de relatório ainda baseadas em `X-API-Key`.

Usuários finais devem usar JWT. Para cada consumidor legítimo restante, registrar proprietário,
escopo e forma de atualização sem copiar o segredo para tickets ou logs.

## Execução

No Cloud Shell, a partir do repositório validado, use a automação fail-closed:

```bash
bash infra/gcp/rotate-operations-key.sh
```

O comando exige confirmação exata, gera 384 bits de entropia sem imprimir a chave, cria uma nova
versão, atualiza somente o secret da revisão Cloud Run e valida `/health`, `/ready`, autenticação
da chave nova, rejeição da anterior, smoke e watchdog. Se um gate falhar, restaura a versão
anterior na API e desabilita de forma reversível a versão nova. Neon e Cloudflare não fazem parte
desta operação.

Fluxo manual de referência:

```bash
set -Eeuo pipefail
export GCP_PROJECT_ID=mplacas
export GCP_REGION=us-central1
export GCP_SERVICE_NAME=mplacas-api

previous_version="$(
  gcloud secrets versions list mplacas-operations-api-key \
    --project "$GCP_PROJECT_ID" \
    --filter='state=ENABLED' \
    --sort-by='~createTime' \
    --limit=1 \
    --format='value(name.basename())'
)"
test -n "$previous_version"

key_file="$(mktemp)"
chmod 600 "$key_file"
python3 -c 'import secrets; print(secrets.token_urlsafe(48))' >"$key_file"
new_version="$(
  gcloud secrets versions add mplacas-operations-api-key \
    --project "$GCP_PROJECT_ID" \
    --data-file="$key_file" \
    --format='value(name.basename())'
)"
rm -f "$key_file"
test -n "$new_version"

gcloud run services update "$GCP_SERVICE_NAME" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --update-secrets="MPLACAS_OPERATIONS_API_KEY=mplacas-operations-api-key:latest"
bash infra/gcp/verify-deployment.sh
```

Atualizar os consumidores confirmados por canal seguro e testar health, readiness, login JWT e as
operações administrativas essenciais. Nunca imprimir `key_file`, variáveis de chave ou respostas
que contenham credenciais.

## Rollback

Se um consumidor crítico falhar, apontar temporariamente o serviço para a versão anterior:

```bash
gcloud run services update "$GCP_SERVICE_NAME" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --update-secrets="MPLACAS_OPERATIONS_API_KEY=mplacas-operations-api-key:${previous_version}"

bash infra/gcp/verify-deployment.sh
```

Não destruir versões durante a janela de observação. Depois da validação e do prazo acordado,
desabilitar a versão anterior; destruição permanente exige uma mudança separada e auditada.

## Evidência da rotação de 2026-08-02

- Inventário encontrou zero chamadas a `/operations/*` em 90 dias e nenhum secret READ separado.
- Somente `mplacas-runtime@mplacas.iam.gserviceaccount.com` possui `secretAccessor` no secret.
- API e 11 jobs apontavam para `mplacas-operations-api-key:latest`.
- A versão 2 foi criada sem exposição e a revisão `mplacas-api-00013-5g6` recebeu 100% do tráfego.
- `/health`, `/ready` e a chave nova retornaram HTTP 200; a versão anterior foi rejeitada com 401.
- `mplacas-smoke-hq4xr` e `mplacas-operational-watchdog-pm2j5` concluíram com sucesso.
- Encerrada a janela de validação, a versão 1 foi desativada de forma reversível e a versão 2
  permaneceu como única versão habilitada; nenhuma versão foi destruída.
- O deploy padrão subsequente passou pelo preflight de versão única e publicou a revisão
  `mplacas-api-00014-f9p` com 100% do tráfego. `/health` e `/ready` retornaram HTTP 200;
  `mplacas-smoke-9x4bn` e `mplacas-operational-watchdog-pwqv8` concluíram com sucesso.
