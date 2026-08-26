# ADR-076 — Saída do Google Cloud e remoção de todo acoplamento ao provedor

## Status

**Aceito — 2026-08-26.** Decisão do usuário (dono do produto e responsável financeiro) após
cobrança não prevista no projeto GCP `mplacas`, sem orçamento para sustentá-la.

A decisão aceita aqui é **sair do Google Cloud e remover o acoplamento no código**. A escolha da
plataforma substituta é **explicitamente deixada em aberto** — ver § *Decisão em aberto*.

## Contexto

### Estado verificado no provedor em 2026-08-26

Verificado via `gcloud` autenticado como o dono da conta, antes de qualquer alteração:

| Fato | Evidência |
|---|---|
| Faturamento do projeto já desativado | `gcloud billing projects describe mplacas` → `billingEnabled: false` |
| Ambas as contas de faturamento fechadas | `gcloud billing accounts list` → `OPEN: False` nas duas |
| API de produção fora do ar | `GET https://mplacas-api-…run.app/health` → **HTTP 500** |
| Serviço e 12 jobs ainda declarados, porém inertes | `gcloud run services list`, `gcloud run jobs list` |
| Scheduler, Secret Manager e Artifact Registry inacessíveis | `PERMISSION_DENIED … reason: BILLING_DISABLED` |

Consequência: **a cobrança já cessou antes desta mudança** e nenhuma alteração no repositório
poderia tê-la interrompido — recurso em nuvem cobra por existir, não por estar citado no código.
Em contrapartida, **a produção está parada desde então**, e é isso que precisa de solução.

### Correção de uma premissa

A motivação relatada foi "remover o banco de dados online do Google Cloud". O banco **nunca esteve
no Google Cloud**: é o Neon (`ADR-051`), em free tier, fora do escopo desta cobrança. O que estava
no GCP e gerava custo era a camada de execução — Cloud Run (serviço web e 12 jobs), Cloud Scheduler,
Secret Manager e Artifact Registry.

Isso não invalida a decisão: a saída do GCP elimina a origem real do custo. Mas define corretamente
o que precisa ser substituído (**execução e agendamento**) e o que **não** precisa (**o banco**).

## Decisão

Remover do repositório todo acoplamento ao Google Cloud, mantendo a aplicação portátil e pronta
para receber uma plataforma nova, sem reescrita.

### O que foi removido

- `infra/gcp/` inteiro — 21 arquivos versionados de provisionamento, deploy, custo e drill, mais o
  `config.env` local não versionado (continha identificadores reais de canal de notificação).
- `.gcloudignore`, e a entrada `/infra/gcp` do Dependabot.
- Job `gcp-deployment-contract` do CI e os 3 arquivos de teste que validavam scripts agora
  inexistentes (708 linhas).
- 3 dependências diretas do Google, que arrastavam **21 pacotes transitivos** — incluindo `grpcio`,
  `protobuf`, `cryptography`, `requests` e `urllib3`. Redução relevante de superfície de suprimento.
- `GcsArtifactStorage` e o Secret Manager em `scripts/set-admin-password.py`.
- Runbooks exclusivos de Cloud Monitoring (SLO e watchdog drill) e o documento de guardrails de custo.

### O que foi substituído por equivalente neutro

| Antes (Google) | Agora (neutro) |
|---|---|
| Exportador Cloud Trace | OTLP genérico, extra opcional `mplacas[otlp]`, import preguiçoso |
| Exportador Cloud Monitoring | idem |
| Header `X-Cloud-Trace-Context` | W3C `traceparent` (já existia em paralelo) |
| Campos `logging.googleapis.com/*` | `trace_id` / `span_id` no JSON de stdout |
| `MPLACAS_GCP_PROJECT_ID` | `MPLACAS_OTLP_ENDPOINT` |
| `cloud_trace_enabled` / `cloud_metrics_enabled` | `tracing_enabled` / `metrics_enabled` |
| `GcsArtifactStorage` (URL assinada v4) | `LocalDirectoryArtifactStorage` (`file://`) |
| Secret Manager no script de senha | leitura por stdin (encadeia qualquer cofre) |
| Módulo `mplacas.cloud_run` | `mplacas.server` |

O extra `otlp` ficou **fora do lock de runtime de propósito**: o projeto roda sem backend de
observabilidade, e o import só executa quando `MPLACAS_OTLP_ENDPOINT` está configurado.

### O que foi preservado intencionalmente

- **Neon** como banco (`ADR-051`) — não é GCP, não é a origem do custo, continua em free tier.
- **Cloudflare Pages** para o frontend — já era fora do GCP e permanece.
- **Telegram** como canal de alerta — não depende de provedor de nuvem.
- A validação que exige TLS em host remoto de banco, que vive em `src/mplacas/db/connection.py`
  (commit `aa54d03`) e **não** no validador que foi removido junto de `infra/gcp/`.
- ADRs, auditorias e checklists datados — são registro histórico e não foram reescritos; os que
  descreviam decisões revogadas foram marcados como substituídos (`ADR-025`, `ADR-026`) ou
  parcialmente substituídos (`ADR-041`, `ADR-042`).

## Decisão em aberto (requer o usuário)

**Nenhuma plataforma substituta foi escolhida.** A aplicação está portátil, mas sem destino. Três
necessidades precisam de resposta, e elas são separáveis:

1. **API HTTP** — servir o dashboard. Único consumidor real hoje: o próprio dono da usina.
2. **Agendamento** — 7 jobs recorrentes (coleta, pipeline diário, digest, drain de outbox e de
   exports, watchdog, retenção). São lote, não exigem servidor sempre ligado.
3. **Cofre de segredos** — credencial NEPViewer, URL do banco, chave operacional, token do Telegram.

O ponto de partida recomendado é reconhecer que **(2) é o volume de trabalho e não precisa de
servidor**: agendador de CI (ex.: GitHub Actions, já disponível e gratuito no repositório, com
segredos próprios) cobre os 7 jobs sem host algum. Isso reduz o problema a hospedar apenas a API.

Qualquer free tier citado numa avaliação futura **deve ser reconferido na fonte antes do
compromisso** — as condições mudam e a cobrança inesperada que originou este ADR é exatamente o
custo de não fazer isso.

## Riscos aceitos

- **Produção parada.** Não é regressão desta mudança: a API já retornava 500 por faturamento
  desativado. Mas segue sem previsão de retorno até a decisão acima.
- **Sem alerta operacional externo.** As políticas de Cloud Monitoring foram removidas. Nada observa
  a aplicação de fora hoje — condição que já era conhecida e agora é total.
- **Sem armazenamento de objetos.** Exports voltam a ser persistidos no banco (comportamento padrão
  que já existia) ou em disco local. Para volume maior, implementar uma classe aderente ao Protocol
  `ArtifactStorage` — nada além dela precisa mudar.
- **Recursos ainda declarados no projeto GCP.** Inertes com faturamento desativado. Reativar o
  faturamento os traria de volta; a limpeza definitiva no console fica como tarefa do usuário.

## Consequências

- O repositório não contém mais nenhuma referência funcional ao Google Cloud.
- Ruff, Mypy e a suíte de testes passam limpos após a remoção.
- Adotar a próxima plataforma não deve exigir mudança no código da aplicação — apenas Dockerfile,
  variáveis de ambiente e um agendador.
