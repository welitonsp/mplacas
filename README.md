# Mplacas

Plataforma de inteligência, auditoria e gestão energética residencial.

## Objetivo

Consolidar telemetria da NEPViewer, dados climáticos e faturas da Equatorial para produzir histórico próprio, conciliação energética, diagnósticos determinísticos, alertas e relatórios auditáveis.

## Estado atual

O projeto possui uma API FastAPI assíncrona com:

- conector isolado para a API NEPViewer v2;
- coleta intradiária, consolidação D+1 e backfill;
- PostgreSQL em produção e SQLite para desenvolvimento/testes;
- persistência idempotente de produção, clima, faturas, alertas e execuções;
- parser determinístico de faturas Equatorial;
- recebimento seguro de texto e PDF pelo Telegram;
- confirmação humana obrigatória de faturas;
- isolamento multiusina por `plant_id`;
- conciliação energética por ciclo de leitura;
- indicadores de produção, consumo, importação, injeção e autossuficiência;
- índice de saúde e diagnósticos determinísticos;
- histórico e tendências entre ciclos;
- dashboard web responsivo;
- relatório mensal auditável em JSON e CSV;
- rastreabilidade de métricas por fonte, natureza, unidade, período e versão;
- correlação climática e detecção de anomalias;
- coleta histórica pelo Open-Meteo;
- explicações assistidas por IA com grounding e fallback determinístico;
- alertas Telegram com deduplicação SQL;
- orquestração diária com lock por usina/data, retomada após timeout e status consultável;
- imagem de produção e comandos de jobs prontos para implantação no Google Cloud Run;
- automação segura de implantação pelo Google Cloud Shell, sem Docker ou `gcloud` no Windows;
- CI com Ruff, Mypy, Pytest, validação Bash, ShellCheck e smoke test do contêiner.

> A API NEPViewer usada é uma interface web não oficial e pode mudar. O adaptador permanece isolado para impedir acoplamento do restante do sistema.

## Princípios de confiabilidade

- cálculos monetários e energéticos usam `Decimal`;
- IA generativa não calcula indicadores, não altera severidades e não atribui causas técnicas;
- dados ausentes, provisórios ou indisponíveis permanecem explícitos;
- reexecuções não duplicam energia, clima, faturas ou alertas;
- relatórios e exportações não recalculam indicadores;
- endpoints operacionais falham fechados quando a chave não está configurada;
- credenciais, PDFs, endereços, CPF e payloads privados não são persistidos em logs ou respostas.

## Endpoints principais

### Operação

- `GET /health`
- `GET /ready`
- `GET /operations/status`
- `GET /operations/jobs`

### Energia e dashboard

- `GET /energy/cycles/{bill_id}`
- `GET /energy/trends/latest`
- `GET /energy/executive/latest`
- `GET /energy/anomalies/latest`
- `GET /energy/explanations/latest`
- `GET /dashboard`

### Relatórios e exportações

- `GET /reports/monthly/latest`
- `GET /reports/monthly/latest.csv`

O relatório mensal usa o mesmo resultado determinístico do painel executivo. Cada indicador inclui
valor, unidade, natureza e fonte. A resposta também registra mês de referência, identificadores da
usina e da fatura, versão do esquema, versão do cálculo, qualidade dos dados, diagnósticos, ações
prioritárias e tendência quando existem dois ciclos confirmados.

O CSV usa UTF-8 com BOM, é entregue como anexo e não pode ser armazenado em cache pelo cliente.

### Clima e pipeline

- `POST /climate/collect`
- `POST /pipeline/run`
- `GET /pipeline/status/latest`

### Alertas e Telegram

- `POST /alerts/run`
- `POST /telegram/webhook`

### Faturas

- intake textual e documental;
- listagem de pendências;
- confirmação, rejeição e atribuição de fatura legada por usina.

Os endpoints operacionais e administrativos exigem `X-API-Key` quando aplicável.

## Ciclo diário recomendado

1. Coletar e consolidar produção da NEPViewer.
2. Executar `POST /pipeline/run` para a usina e data-alvo.
3. O pipeline adquire lock persistente por usina/data.
4. Dados climáticos são coletados e persistidos de forma idempotente.
5. Diagnósticos e anomalias são recalculados pelos motores determinísticos.
6. Alertas elegíveis são enviados e deduplicados pelo ledger SQL.
7. A execução termina como `SUCCEEDED` ou `FAILED` e pode ser consultada em `/pipeline/status/latest`.
8. Locks `RUNNING` abandonados somente são retomados após o timeout configurado.

## Explicações assistidas por IA

O endpoint `/energy/explanations/latest` sempre consegue responder com fallback determinístico. Quando `MPLACAS_EXPLANATION_API_URL` estiver configurada, o sistema envia ao gateway apenas evidências normalizadas e exige JSON estruturado com:

```json
{
  "summary": "...",
  "what_it_means": "...",
  "next_steps": ["..."]
}
```

A aplicação substitui qualquer aviso do provedor por um disclaimer fixo e limita as recomendações a cinco itens.

## Execução local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
uvicorn mplacas.main:app --reload
```

Acesse:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ready`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/dashboard`

## Contêiner e Cloud Run

A imagem de produção usa usuário não root e inicia a API com:

```bash
python -m mplacas.cloud_run
```

O processo escuta em `0.0.0.0` e usa `PORT`, com fallback local 8080.

Build local opcional:

```bash
docker build -t mplacas-cloud-run:local .
```

A implantação oficial não exige Docker local. Os scripts em `infra/gcp/` executam o fluxo pelo
Google Cloud Shell e usam build gerenciado com `gcloud run deploy --source`.

Guardrails iniciais obrigatórios:

- região `us-central1`;
- mínimo de 0 instâncias;
- máximo de 1 instância;
- 1 CPU;
- 512 MiB de memória;
- service account de runtime dedicada;
- segredos no Secret Manager com IAM por segredo;
- nenhuma criação de Compute Engine, Cloud SQL, load balancer dedicado ou Scheduler.

Cloud Run Jobs disponíveis:

```bash
python -m mplacas.cloud_jobs migrate
python -m mplacas.cloud_jobs daily-pipeline
```

A migração é executada explicitamente por Cloud Run Job e nunca no startup do serviço web. O
Scheduler futuro deve acionar jobs autenticados por IAM, não endpoints administrativos públicos.

Documentação operacional:

- `docs/RUNBOOK_GOOGLE_CLOUD_DEPLOYMENT.md` — implantação completa pelo Cloud Shell;
- `docs/ADR-026-google-cloud-deployment-automation.md` — decisão e controles da automação;
- `docs/RUNBOOK_GOOGLE_CLOUD_RUN.md` — arquitetura e operação da plataforma;
- `docs/COST_GUARDRAILS_GOOGLE_CLOUD.md` — controles de custo;
- `docs/ADR-025-google-cloud-run-platform.md` — decisão da plataforma.

## Banco

O padrão de desenvolvimento é SQLite. Para PostgreSQL:

```text
MPLACAS_DATABASE_URL=postgresql+asyncpg://usuario@host:5432/mplacas
```

Execute sempre:

```bash
alembic upgrade head
```

antes de iniciar uma nova versão da aplicação.

## Configuração sensível

Nunca registre no GitHub:

- senha da NEPViewer;
- chave operacional;
- token do Telegram;
- chave do gateway de IA;
- faturas de energia;
- CPF, endereço ou unidade consumidora;
- dumps de respostas externas;
- `infra/gcp/config.env`;
- valores usados no Secret Manager.

Use variáveis de ambiente ou secrets da hospedagem. Consulte `.env.example` para os nomes suportados.

## Auditoria e decisões

- ADRs: diretório `docs/`;
- relatório mensal e CSV: `docs/ADR-027-monthly-reports-and-csv-export.md`;
- auditoria das PRs nº 1 a nº 28: `docs/AUDITORIA_PRS_01_28_2026-07-13.md`;
- checkpoint histórico: `docs/CHECKPOINT_PROJETO_2026-07-12.md`.

## Regra de entrega

Uma PR somente é considerada concluída quando todo o seu escopo está implementado, testado, documentado, validado pelo CI e mergeado. Não são iniciadas novas funcionalidades enquanto houver pendência conhecida da etapa atual.
