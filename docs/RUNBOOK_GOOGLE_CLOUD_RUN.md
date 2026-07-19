# Runbook Google Cloud Run

## Objetivo

Preparar e operar o Mplacas em Google Cloud Run com API stateless, Cloud Run Jobs para
tarefas operacionais, Cloud Scheduler como acionador e Neon PostgreSQL como banco
PostgreSQL gerenciado. Este documento não cria recursos automaticamente.

## Arquitetura

```text
Usuário HTTPS
    -> Cloud Run service
    -> Mplacas FastAPI e dashboard
    -> Neon PostgreSQL

Cloud Scheduler
    -> Cloud Run Job
    -> Mplacas pipeline
    -> Neon PostgreSQL
```

## Pré-requisitos

- Projeto Google Cloud com billing habilitado.
- Artifact Registry, Cloud Run, Cloud Scheduler e Secret Manager habilitados.
- Banco Neon PostgreSQL criado e migrado por Alembic.
- Service accounts dedicadas para serviço web, jobs e scheduler.
- Segredos armazenados no Secret Manager.
- Região definida antes do deploy, por exemplo `us-central1`.

## Free Tier e cobrança

Use instâncias mínimas iguais a zero e limite inicial de uma instância. Não crie Cloud SQL,
Compute Engine, load balancer ou NAT nesta implantação. Configure orçamento e alertas antes
de publicar qualquer serviço.

## Build

Bash:

```bash
docker build -t mplacas-cloud-run:local .
```

PowerShell:

```powershell
docker build -t mplacas-cloud-run:local .
```

A imagem inicia com:

```text
python -m mplacas.cloud_run
```

O contêiner lê `PORT` e escuta em `0.0.0.0`. Migrações e coletas não rodam no startup.

## Variáveis e segredos

Variáveis não sensíveis:

```text
MPLACAS_ENVIRONMENT=production
MPLACAS_TIMEZONE=America/Sao_Paulo
MPLACAS_LOG_LEVEL=INFO
MPLACAS_EXTERNAL_HTTP_ALLOWED_HOSTS=api.nepviewer.net,archive-api.open-meteo.com
PORT=8080
MPLACAS_READINESS_TIMEOUT_SECONDS=3
```

Segredos previstos no Secret Manager:

- `DATABASE_URL`
- `OPERATIONS_API_KEY`
- `OPERATIONS_READ_API_KEY` opcional para consumidores somente leitura
- `NEP_ACCOUNT`
- `NEP_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `EXPLANATION_API_KEY`

Mapeie os segredos para variáveis `MPLACAS_DATABASE_URL`,
`MPLACAS_OPERATIONS_API_KEY`, `MPLACAS_OPERATIONS_READ_API_KEY` quando houver consumidores somente
leitura, `MPLACAS_NEP_ACCOUNT`, `MPLACAS_NEP_PASSWORD`,
`MPLACAS_TELEGRAM_BOT_TOKEN`, `MPLACAS_TELEGRAM_WEBHOOK_SECRET` e
`MPLACAS_EXPLANATION_API_KEY`.

Quando a chave de leitura não puder consultar todas as usinas, configure também a variável não
secreta `MPLACAS_OPERATIONS_READ_PLANT_IDS` com os UUIDs autorizados separados por vírgula. Uma lista
inválida, vazia ou configurada sem `MPLACAS_OPERATIONS_READ_API_KEY` impede a inicialização. A ausência
da variável mantém o acesso de leitura global por compatibilidade.

Não use arquivo JSON de chave de service account no repositório ou na imagem.

## Deploy do serviço

Exemplo Bash, substituindo os identificadores pelo ambiente real:

```bash
gcloud run deploy mplacas-api \
  --image "$IMAGE_URI" \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars MPLACAS_ENVIRONMENT=production,MPLACAS_TIMEZONE=America/Sao_Paulo \
  --service-account "$RUNTIME_SERVICE_ACCOUNT"
```

Use Secret Manager para as variáveis sensíveis em vez de `--set-env-vars`.

## Health e readiness

- `GET /health`: confirma que processo e runtime HTTP responderam.
- `GET /ready`: valida configuração e conectividade com PostgreSQL com timeout.

`/ready` retorna 503 quando o banco não responde ou a configuração não é válida. A resposta
não inclui URL, senha, token ou stack trace.

## Migração por Cloud Run Job

O job de migração executa:

```bash
python -m mplacas.cloud_jobs migrate
```

Ele roda `alembic upgrade head`, registra logs sanitizados e encerra com exit code diferente
de zero em falha.

## Pipeline diário por Cloud Run Job

O job operacional executa:

```bash
python -m mplacas.cloud_jobs daily-pipeline
```

Configuração esperada:

```text
MPLACAS_CLOUD_JOB_PLANT_ID=<uuid-da-usina>
MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH=<decimal>
MPLACAS_CLOUD_JOB_EXPECTED_CYCLE_PRODUCTION_KWH=<decimal opcional>
MPLACAS_CLOUD_JOB_ANOMALY_DAYS=7
```

Sem `--target-date`, o job usa o dia anterior em `MPLACAS_TIMEZONE`. Para reprocessamento
controlado:

```bash
python -m mplacas.cloud_jobs daily-pipeline --target-date 2026-07-13
```

## Cloud Scheduler

Configure o Scheduler para acionar o Cloud Run Job com IAM, usando service account dedicada
e menor privilégio. Use timezone `America/Sao_Paulo`, execução diária, retry limitado e
timeout compatível com a janela operacional. Não exponha endpoint público sem autenticação
para tarefas administrativas.

A prevenção de sobreposição usa o lock persistente por `plant_id` e `target_date` já
existente no pipeline.

## Rollback

Mantenha a revisão anterior do Cloud Run disponível. Para rollback do serviço web, direcione
tráfego para a revisão anterior. Para jobs, reimplante a imagem anterior e execute a
migração somente quando a versão exigir.

## Logs e troubleshooting

Use Cloud Logging. Os logs de aplicação registram códigos técnicos e metadados operacionais
seguros. Eles não devem conter URL completa de banco, senha, token, PDF, fatura ou payload
externo.

Falhas comuns:

- `/ready` 503: validar Secret Manager, Neon, rede pública permitida e SSL do PostgreSQL.
- Migração falha: revisar Alembic e permissões do usuário do banco.
- Job diário falha: validar `MPLACAS_CLOUD_JOB_PLANT_ID`, produção esperada, Telegram e lock.
- Custo inesperado: revisar instâncias mínimas, instâncias máximas, região e serviços ativos.

## Remoção de recursos

Para evitar cobrança, remova serviços Cloud Run, jobs, scheduler, Artifact Registry sem uso,
secrets antigos e alertas desnecessários. Confirme que não há Cloud SQL, Compute Engine,
load balancer ou discos persistentes criados para esta aplicação.

## Segurança

- Não versionar segredos.
- Não criar arquivos de chave JSON.
- Usar service accounts dedicadas.
- Conceder apenas permissões necessárias.
- Não armazenar dados persistentes no filesystem do contêiner.
- Usar `/tmp` apenas para temporários efêmeros.
