# ADR-076 — Saída do Google Cloud e remoção de todo acoplamento ao provedor

## Status

**Aceito — 2026-08-26.** Decisão do usuário (dono do produto e responsável financeiro) após
cobrança não prevista no projeto GCP `mplacas`, sem orçamento para sustentá-la.

Duas decisões, ambas aceitas: **sair do Google Cloud e remover o acoplamento no código**, e
**adotar a arquitetura gratuita descrita em § _Plataforma substituta_**, escolhida em 2026-08-26
após verificação nas fontes primárias de cada provedor.

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
- A proibição de usar o Google Cloud, que vivia em `infra/gcp/ZERO_COST_POLICY.md` e foi promovida
  a `docs/POLITICA_SEM_GOOGLE_CLOUD.md`. Mudou de lugar porque o diretório `infra/gcp/` deixou de
  existir; **não** mudou de força. Revogá-la exige ADR novo aceitando a possibilidade de cobrança.
- ADRs, auditorias e checklists datados — são registro histórico e não foram reescritos; os que
  descreviam decisões revogadas foram marcados como substituídos (`ADR-025`, `ADR-026`) ou
  parcialmente substituídos (`ADR-041`, `ADR-042`).

## Plataforma substituta

Restrição do usuário: **sem orçamento**. A solução precisa ser gratuita de verdade, não trial.

### Verificação feita nas fontes primárias em 2026-08-26

Opções descartadas, com o motivo verificado — não por memória:

| Opção | Por que caiu |
|---|---|
| Fly.io | Free tier **descontinuado em 2024-10-07**; em 2026 só há trial de 2 h de VM ou 7 dias |
| Koyeb | Adquirida pela Mistral AI no início de 2026; tier Starter gratuito **fechado a novos usuários** |
| Oracle Always Free | **Recupera instância ociosa** quando CPU (p95), rede e memória ficam abaixo de 20% por 7 dias — exatamente o perfil de uma API de um único usuário. Além disso cortou o limite de 4 OCPU/24 GB para 2 OCPU/12 GB em 2026-06-15, sem aviso público, com e-mails de terminação para quem excedesse |
| Cron job no Render | Recurso **pago**; o plano free cobre apenas web service, Postgres e key-value |

### Arquitetura adotada

A peça que destrava tudo: **o repositório é público**, e Actions em runner padrão é gratuito e
ilimitado para repositório público. Os 8 jobs são lote e não precisam de servidor.

| Peça | Onde | Custo |
|---|---|---|
| Frontend | Cloudflare Pages | grátis (já estava) |
| Banco | Neon free tier | grátis (já estava, nunca foi GCP) |
| API HTTP | Render, plano free, Docker | grátis, **sem cartão** |
| 8 jobs operacionais | GitHub Actions cron | grátis e ilimitado (repo público) |
| Migrações | GitHub Actions, acionamento manual | idem |
| Segredos da API | variáveis do Render marcadas `sync: false` | grátis |
| Segredos dos jobs | GitHub Secrets | grátis |
| Alerta operacional | notificação de falha do GitHub Actions + Telegram | grátis |

Arquivos: `render.yaml`, `.github/workflows/operational-jobs.yml`, `.github/workflows/migrate.yml`.

### Mudança de desenho nos jobs, deliberada

No GCP eram 8 agendas independentes separadas por 4 minutos, e a ordem correta dependia de nenhuma
atrasar. Agora são **passos sequenciais de um único job**: a ordem é garantida por construção, e um
único gatilho de cron reduz a exposição ao descarte de agendas que o GitHub admite em carga alta.
Cada passo usa `if: always()`, então a falha de um não impede os seguintes, mas derruba o workflow —
e a notificação de falha do GitHub vira o alerta externo que as policies de Cloud Monitoring faziam.

O horário passou para **06:07 em `America/Sao_Paulo`**, usando o suporte nativo do GitHub Actions a
timezone IANA. O minuto 7 é proposital: o GitHub documenta que agendas no topo da hora atrasam e
podem ser descartadas.

### Limitações conhecidas desta escolha

- **Cold start.** O web service free do Render hiberna após 15 min sem tráfego; a primeira
  requisição seguinte leva de 30 a 60 s. Aceito: o dashboard tem um usuário. **Não** criar keep-alive
  para contornar — consumiria as 750 h/mês (o mês tem ~730) e manteria o Neon acordado, que é
  exatamente o que estourou a cota de compute em 2026-08-21.
- **Agendas somem após 60 dias de repositório parado.** O GitHub desabilita automaticamente
  workflows agendados em repositório público sem atividade por 60 dias. O sinal prático de que isso
  aconteceu é o **digest diário parar de chegar no Telegram**. Reabilitar é manual, na aba Actions.
- **Repositório público.** Nenhum segredo pode entrar no Git. Por isso todo valor sensível está em
  GitHub Secrets ou marcado `sync: false` no `render.yaml`. O gitleaks no CI já guarda essa regra.

## Riscos aceitos

- **Produção parada até a execução do runbook.** Não é regressão desta mudança: a API já retornava
  500 por faturamento desativado. O caminho de volta está em `docs/RUNBOOK_DEPLOY.md`.
- **Alerta operacional mais fraco que antes.** No lugar das policies de Cloud Monitoring ficam a
  notificação de falha do GitHub Actions e o digest diário no Telegram. Cobre a falha do ciclo
  operacional, mas **não** cobre a API cair de pé — segue valendo `mplacas-sem-uptime-check`.
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
