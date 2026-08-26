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
- faturas sempre vinculadas a uma usina por `plant_id`;
- isolamento multiusina por `plant_id`;
- conciliação energética por ciclo de leitura;
- indicadores de produção, consumo, importação, injeção e autossuficiência;
- índice de saúde e diagnósticos determinísticos;
- histórico e tendências entre ciclos;
- dashboard web responsivo;
- relatório mensal auditável em JSON, CSV, PDF e XLSX;
- rastreabilidade de métricas por fonte, natureza, unidade, período e versão;
- correlação climática e detecção de anomalias;
- coleta histórica pelo Open-Meteo;
- explicações assistidas por IA com grounding e fallback determinístico;
- alertas Telegram com outbox transacional, retry e deduplicação SQL;
- métricas OpenTelemetry de duração e resultado por operação, exportáveis por OTLP;
- credenciais operacionais persistidas com papéis, escopo por usina, revogação e auditoria;
- usuários operacionais nomeados com credenciais associadas, expiração e desativação em cascata;
- fila de coleta no Postgres com claim atômico, backoff e isolamento de falha por usina;
- camada de resiliência da coleta NEPViewer: retry com backoff, detecção de dados incompletos e reagendamento;
- job de coleta (`collect`) que compõe a resiliência e defere para a fila quando a API persiste indisponível;
- job de drenagem (`drain-collection`) que reprocessa os dias deferidos, isolando cada tarefa em sua transação;
- job de retenção (`retention`) que remove registros operacionais terminais e antigos, preservando produção e dados em andamento;
- read-model do dashboard executivo com cache invalidado por impressão digital dos dados (nunca serve resultado obsoleto);
- alertas de SLO documentados por runbook para falhas de pipeline, despacho e latência;
- orquestração diária com lock por usina/data, retomada após timeout e status consultável;
- logs JSON correlacionados, trace ID ponta a ponta e spans OpenTelemetry exportáveis por OTLP;
- imagem de contêiner portátil, sem dependência de provedor de nuvem;
- runbook de backup e restauração com teste de ensaio obrigatório em banco descartável;
- CI com Ruff, Mypy, Pytest e smoke test do contêiner.

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
- `GET /operations/status` (`X-API-Key`)
- `GET /operations/jobs` (`X-API-Key`)

### Energia e dashboard

- `GET /energy/cycles/{bill_id}`
- `GET /energy/trends/latest`
- `GET /energy/executive/latest`
- `GET /energy/anomalies/latest`
- `GET /energy/explanations/latest`
- `GET /dashboard` (redireciona para a SPA JWT configurada)

### Relatórios e exportações

- `GET /reports/monthly/latest`
- `GET /reports/monthly/latest.csv`
- `GET /reports/monthly/latest.pdf`
- `GET /reports/monthly/latest.xlsx`

O relatório mensal usa o mesmo resultado determinístico do painel executivo. Quando uma fatura é
confirmada, o sistema persiste na mesma transação um snapshot canônico e imutável do relatório. Para
faturas confirmadas antes dessa funcionalidade, a primeira leitura materializa o snapshot de forma
idempotente. Cada indicador inclui valor, unidade, natureza e fonte. A resposta também registra mês
de referência, identificadores da usina e da fatura, versão do esquema, versão do cálculo, qualidade
dos dados, diagnósticos, ações prioritárias e tendência quando existem dois ciclos confirmados.

O CSV usa UTF-8 com BOM. O PDF é paginado em A4 e registra as versões no rodapé. O XLSX possui abas
separadas para resumo, indicadores, qualidade, diagnósticos, tendências e metadados. Nenhum desses
formatos recalcula indicadores: todos serializam o mesmo snapshot persistido. As respostas expõem o
checksum canônico no `ETag` e o identificador em `X-Mplacas-Report-Snapshot`. Os downloads são
entregues como anexos e não podem ser armazenados em cache pelo cliente. Os parâmetros legados
`expected_production_kwh` e `stable_tolerance_percent` permanecem aceitos, porém estão descontinuados
e não alteram snapshots.

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
- confirmação e rejeição de faturas sempre escopadas por usina.

Os endpoints operacionais e administrativos exigem `X-API-Key`, exceto `/health`, `/ready` e o
redirecionamento `/dashboard`. Usuários finais acessam somente a SPA com JWT e nunca informam uma
chave operacional. `MPLACAS_OPERATIONS_API_KEY` tem papel administrativo e continua global nesta
fase. Consumidores somente leitura, incluindo os restritos a usinas específicas, autenticam com uma
credencial operacional persistida (papel `READ`), emitida via `/operations/credentials` — não há
mais uma chave estática de leitura configurada por variável de ambiente. Quando o escopo de usina da
credencial é restrito, recursos de outras usinas retornam `404` e as visões operacionais globais
retornam `403`.

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

Em produção, endpoints HTTP externos configuráveis precisam usar HTTPS e estar listados em
`MPLACAS_EXTERNAL_HTTP_ALLOWED_HOSTS`. O padrão permite apenas NEPViewer e Open-Meteo; inclua o host
do gateway de explicações somente quando esse provedor for realmente usado.

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
- `http://127.0.0.1:8000/dashboard` (redireciona para `MPLACAS_DASHBOARD_URL`)

## Contêiner e execução

A imagem de produção usa usuário não root e inicia a API com:

```bash
python -m mplacas.server
```

O processo escuta em `0.0.0.0` e usa `PORT`, com fallback local 8080.

Build local opcional:

```bash
docker build -t mplacas-api:local .
```

A imagem não depende de nenhum provedor: qualquer host que execute um contêiner e forneça
`PORT` e as variáveis de ambiente serve. **Não há plataforma de implantação definida no
momento** — ver ADR-076 para o contexto da saída do Google Cloud e as opções em avaliação.

Jobs operacionais disponíveis:

```bash
python -m mplacas.cloud_jobs migrate
python -m mplacas.cloud_jobs daily-pipeline
python -m mplacas.cloud_jobs dispatch-outbox
```

A migração é executada explicitamente por um job e nunca no startup do serviço web. O
`daily-pipeline` persiste eventos de alerta antes da entrega externa. O `dispatch-outbox` recupera
eventos pendentes com lock, retry e backoff exponencial; ele deve ser executado periodicamente para
garantir recuperação mesmo quando o processo original termina após o commit. O agendador que vier
a ser adotado deve acionar jobs autenticados, não endpoints administrativos públicos.

Em produção, cada resposta inclui `X-Request-ID` e `X-Trace-ID`. Os logs JSON vão para stdout com
`trace_id`/`span_id` correlacionados, sem campo específico de provedor. FastAPI, SQLAlchemy, HTTPX e
as etapas do pipeline são instrumentados quando `MPLACAS_TRACING_ENABLED=true` e
`MPLACAS_OTLP_ENDPOINT` aponta para um coletor OTLP (extra `mplacas[otlp]`); a amostragem padrão é 10%.
Query strings não entram nos spans e o token presente no path do Telegram é mascarado.

Documentação operacional:

- `docs/ADR-076-saida-do-google-cloud.md` — saída do Google Cloud e escolha de plataforma em aberto;
- `docs/ADR-025-google-cloud-run-platform.md` e `docs/ADR-026-google-cloud-deployment-automation.md`
  — decisões de plataforma **substituídas**, mantidas como histórico.

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

## Backup e restauração

O contrato operacional de backup e restauração está documentado em
[`docs/backup-restore-runbook.md`](docs/backup-restore-runbook.md). O backup só deve ser considerado
válido após restauração de ensaio em banco descartável, validação de tabelas críticas e sucesso do
`/ready` contra o banco restaurado.

## Configuração sensível

Nunca registre no GitHub:

- senha da NEPViewer;
- chave operacional;
- token do Telegram;
- chave do gateway de IA;
- faturas de energia;
- CPF, endereço ou unidade consumidora;
- dumps de respostas externas;
- valores guardados no cofre de segredos da hospedagem.

Use variáveis de ambiente ou secrets da hospedagem. Consulte `.env.example` para os nomes suportados.

## Auditoria e decisões

- ADRs: diretório `docs/`;
- PDF e XLSX: `docs/ADR-028-pdf-and-xlsx-report-exports.md`;
- segurança de egress e request ID: `docs/ADR-030-production-egress-and-request-tracing.md`;
- papel operacional somente leitura: `docs/ADR-031-operational-read-role-api-key.md`;
- trilha auditável de credencial operacional: `docs/ADR-032-operational-credential-audit-trail.md`;
- auditoria persistente de ações sensíveis: `docs/ADR-033-persistent-sensitive-action-audit.md`;
- auditoria persistente ampliada: `docs/ADR-034-expanded-administrative-audit-events.md`;
- escopo obrigatorio de faturas por usina: `docs/ADR-035-mandatory-utility-bill-plant-scope.md`;
- fronteira de leitura de faturas confirmadas: `docs/ADR-036-confirmed-billing-read-boundary.md`;
- acesso de leitura escopado por usina: `docs/ADR-037-plant-scoped-operational-read-access.md`;
- snapshots imutáveis de relatório: `docs/ADR-038-immutable-monthly-report-snapshots.md`;
- módulos focados de relatório: `docs/ADR-039-focused-monthly-report-modules.md`;
- outbox transacional de alertas: `docs/ADR-040-transactional-alert-outbox.md`;
- observabilidade estruturada: `docs/ADR-041-structured-observability-and-cloud-trace.md` (parcialmente substituído pelo ADR-076);
- relatório mensal e CSV: `docs/ADR-027-monthly-reports-and-csv-export.md`;
- auditoria das PRs nº 1 a nº 28: `docs/AUDITORIA_PRS_01_28_2026-07-13.md`;
- auditoria técnica profunda: `docs/AUDITORIA_TECNICA_PROFUNDA_2026-07-16.md`;
- checkpoint histórico: `docs/CHECKPOINT_PROJETO_2026-07-12.md`;
- checkpoint atual: `docs/CHECKPOINT_PROJETO_2026-07-16.md`.

## Regra de entrega

Uma PR somente é considerada concluída quando todo o seu escopo está implementado, testado, documentado, validado pelo CI e mergeado. Não são iniciadas novas funcionalidades enquanto houver pendência conhecida da etapa atual.
