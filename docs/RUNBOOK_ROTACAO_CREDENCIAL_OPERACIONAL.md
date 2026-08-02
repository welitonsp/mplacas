# Runbook — rotação da credencial operacional

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
- `MPLACAS_OPERATIONS_READ_API_KEY`, se distribuída separadamente.

Usuários finais devem usar JWT. Para cada consumidor legítimo restante, registrar proprietário,
escopo e forma de atualização sem copiar o segredo para tickets ou logs.

## Execução

No Cloud Shell, a partir do repositório validado:

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

bash infra/gcp/deploy-service.sh
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
