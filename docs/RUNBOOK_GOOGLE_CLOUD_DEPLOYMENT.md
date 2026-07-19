# Runbook — Implantação segura do Mplacas no Google Cloud

## Objetivo

Implantar o Mplacas no Google Cloud Run usando somente o navegador e o Google Cloud Shell, sem
instalar Docker ou Google Cloud CLI na estação Windows.

Este runbook separa preparação, segredos, deploy, migração, verificação, auditoria e remoção. Os
comandos são intencionalmente explícitos e exigem confirmações antes de ações que alteram recursos.

## Estado de segurança desta automação

A presença dos scripts no GitHub não cria recursos no Google Cloud. Recursos somente são criados
quando um operador autenticado executa os scripts no Google Cloud Shell e confirma as ações.

A automação não cria Compute Engine, Cloud SQL, load balancer dedicado, VPC Connector, Cloud
Scheduler, chaves de service account, papéis `Owner` ou `Editor`.

## Pré-requisitos administrativos

Antes do primeiro comando:

1. Criar ou selecionar um projeto Google Cloud exclusivo ou adequadamente governado.
2. Confirmar que o billing está vinculado ao projeto.
3. Criar um orçamento mensal baixo e alertas em 50%, 80% e 100% no Console do Google Cloud.
4. Ter pronta uma URL PostgreSQL compatível com `asyncpg`.
5. Gerar uma chave operacional longa e aleatória para `MPLACAS_OPERATIONS_API_KEY`.
6. Não copiar segredos para arquivos versionados, mensagens, issues ou Pull Requests.

## 1. Abrir o Google Cloud Shell

No Console do Google Cloud, abra o Cloud Shell. Confirme a conta autenticada:

```bash
gcloud auth list
```

Clone o repositório e entre no diretório:

```bash
git clone https://github.com/welitonsp/mplacas.git
cd mplacas
```

Depois que a PR nº 32 estiver integrada, use a `main` atualizada:

```bash
git switch main
git pull --ff-only origin main
```

Durante a revisão da PR nº 32, somente para validação do código da branch:

```bash
git switch feat/pr32-google-cloud-deployment
```

## 2. Criar a configuração não sensível

Copie o exemplo:

```bash
cp infra/gcp/config.example.env infra/gcp/config.env
```

Edite apenas os campos necessários:

```bash
nano infra/gcp/config.env
```

Preencha `GCP_PROJECT_ID` com o ID real do projeto. Preserve os guardrails iniciais:

```text
GCP_REGION=us-central1
GCP_MIN_INSTANCES=0
GCP_MAX_INSTANCES=1
GCP_CPU=1
GCP_MEMORY=512Mi
GCP_CONCURRENCY=20
GCP_REQUEST_TIMEOUT=60
MPLACAS_TIMEZONE=America/Sao_Paulo
```

O arquivo `infra/gcp/config.env` é ignorado pelo Git. Mesmo assim, não armazene valores secretos
nele.

## 3. Validar os scripts antes de qualquer alteração na nuvem

Execute:

```bash
for script in infra/gcp/*.sh; do
  echo "Validando ${script}"
  bash -n "$script"
done
```

Quando o ShellCheck estiver disponível:

```bash
shellcheck infra/gcp/*.sh
```

Essas validações não executam comandos `gcloud` contidos nos scripts.

## 4. Preparar APIs e identidade de runtime

Execute, substituindo pelo mesmo projeto configurado em `config.env`:

```bash
bash infra/gcp/bootstrap.sh SEU_PROJECT_ID
```

O script:

- valida a configuração;
- exige autenticação ativa;
- exige confirmação digitada do ID do projeto;
- confirma que o billing está habilitado;
- habilita somente as APIs declaradas;
- cria a service account de runtime quando ausente;
- concede à identidade de runtime somente `roles/cloudtrace.agent` para exportar spans;
- não cria chave de service account.

## 5. Criar ou rotacionar segredos

Execute em terminal interativo:

```bash
bash infra/gcp/set-secrets.sh
```

O script solicitará, sem eco visual:

1. `MPLACAS_DATABASE_URL`;
2. `MPLACAS_OPERATIONS_API_KEY`.

Regras:

- cole cada valor apenas no prompt correspondente;
- não inclua os valores no histórico do shell;
- a nova versão é identificada diretamente pela resposta do Secret Manager;
- a nova versão é confirmada como `ENABLED`;
- versões habilitadas anteriores são desabilitadas;
- versões não são destruídas automaticamente;
- a service account recebe `roles/secretmanager.secretAccessor` em cada segredo individual.

## 6. Implantar o serviço

Execute:

```bash
bash infra/gcp/deploy-service.sh
```

Digite a confirmação exata exibida pelo script.

O deploy:

- usa `gcloud run deploy --source`;
- envia o código-fonte para build gerenciado no Google Cloud;
- não requer Docker local;
- usa a service account dedicada;
- injeta os dois segredos pelo Secret Manager;
- habilita logs JSON e exportação amostrada de spans para o Cloud Trace do projeto;
- fixa min 0, max 1, CPU 1 e memória 512 MiB;
- publica o serviço HTTP;
- valida os limites reais da revisão após a implantação.

Ao final, registre somente a URL pública do serviço. Não copie dados de configuração ou saídas que
possam conter informações sensíveis.

## 7. Executar migrações

Depois que o serviço estiver implantado:

```bash
bash infra/gcp/run-migrations.sh
```

Digite a confirmação exata exibida.

O script cria ou atualiza um Cloud Run Job baseado na mesma imagem implantada e executa:

```text
python -m mplacas.cloud_jobs migrate
```

Características:

- uma tarefa;
- zero retries automáticos;
- timeout de 10 minutos;
- aguarda o término;
- falha com código diferente de zero quando a migração falha;
- não executa migrações no startup do serviço web.

## 8. Verificar a implantação

Execute:

```bash
bash infra/gcp/verify-deployment.sh
```

A verificação exige:

- `/health` com HTTP 200 e `status=ok`;
- `/ready` com HTTP 200 e `status=ready`;
- `/dashboard` com HTTP 200;
- ausência de padrões sensíveis nas respostas;
- min 0;
- max 1;
- CPU 1;
- memória 512 MiB;
- service account esperada.

As respostas também devem conter `X-Request-ID` e `X-Trace-ID`. No Cloud Logging, filtre por
`jsonPayload.trace_id` e use o link de trace associado para inspecionar FastAPI, SQLAlchemy, HTTPX e
as etapas do pipeline.

## 9. Auditar custos e recursos proibidos

Execute:

```bash
bash infra/gcp/audit-costs.sh
```

O script é somente leitura. Ele:

- valida os guardrails do serviço quando implantado;
- informa a presença do job de migração;
- lista repositórios do Artifact Registry na região;
- exige exatamente uma versão habilitada por segredo gerenciado;
- falha se encontrar recursos Mplacas em Cloud SQL, Compute Engine, load balancer, VPC Connector
  ou Cloud Scheduler, quando as APIs correspondentes estiverem habilitadas.

A auditoria não substitui a análise do painel de billing. Revise custos e uso no Console após o
primeiro deploy e novamente no dia seguinte.

## 10. Atualizar uma versão futura

Após uma nova PR ser integrada:

```bash
git switch main
git pull --ff-only origin main
bash infra/gcp/deploy-service.sh
bash infra/gcp/run-migrations.sh
bash infra/gcp/verify-deployment.sh
bash infra/gcp/audit-costs.sh
```

Execute migração somente quando a versão contiver mudanças compatíveis e revisadas no schema.

## 11. Rotacionar segredos

Para rotacionar banco ou chave operacional, execute novamente:

```bash
bash infra/gcp/set-secrets.sh
bash infra/gcp/deploy-service.sh
bash infra/gcp/verify-deployment.sh
```

A rotação não destrói versões antigas. A exclusão definitiva deve ser uma decisão administrativa
separada, após confirmar que não há necessidade de rollback ou auditoria.

## 12. Remover recursos de runtime

Por padrão, preserve os segredos:

```bash
bash infra/gcp/destroy-resources.sh
```

Digite a confirmação exata exibida. O script remove somente o serviço e o job nomeados do
Mplacas. Projeto, billing, Artifact Registry e segredos permanecem.

Para excluir também os dois segredos nomeados do Mplacas:

```bash
bash infra/gcp/destroy-resources.sh --delete-secrets
```

Use essa opção somente após verificar backups, necessidade de rollback e impacto operacional.

O Artifact Registry nunca é removido automaticamente. Revise imagens e repositórios manualmente
no Console antes de qualquer exclusão.

## 13. Checklist de encerramento

Após implantação bem-sucedida:

- CI da PR aprovado;
- branch integrada à `main`;
- orçamento e alertas ativos;
- serviço com min 0 e max 1;
- CPU 1 e memória 512 MiB;
- service account dedicada;
- exatamente uma versão habilitada por segredo;
- `/health`, `/ready` e `/dashboard` aprovados;
- migração concluída;
- auditoria de custos aprovada;
- nenhum Cloud SQL, Compute Engine, load balancer, VPC Connector ou Scheduler do Mplacas;
- nenhum segredo copiado para GitHub, documentação ou logs.

## Resposta a incidentes

Se o serviço falhar após o deploy:

1. não rotacione nem exclua segredos durante o diagnóstico;
2. consulte logs do Cloud Run sem copiar payloads sensíveis;
3. verifique `/health` e `/ready` separadamente;
4. confirme a conectividade do PostgreSQL;
5. confirme que a migração terminou com sucesso;
6. execute `audit-costs.sh` para confirmar os guardrails;
7. reverta para uma revisão anterior pelo Console ou faça novo deploy de um commit conhecido;
8. documente causa, impacto, correção e evidências sem expor credenciais.
