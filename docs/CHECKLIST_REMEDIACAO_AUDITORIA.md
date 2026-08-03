# Checklist de remediação — Auditorias técnicas Mplacas

Última atualização: 2026-08-02 (Neon e Cloudflare endurecidos; rollout RLS ainda parcial)

Base do novo ciclo: `HEAD b73e97e`. Implementação integrada em `main` pelo merge commit
`b888b4b3c91244a6c2fd87b7d77c9a11ed367186`, via
[#68](https://github.com/welitonsp/mplacas/pull/68).

Relatório atual: `AUDITORIA_BIG_TECH_2026-08-01.md`.

Este arquivo preserva o fechamento da auditoria histórica de 2026-07-16 e passa a rastrear também
o ciclo BIG TECH de 2026-08-01. Não reabrir itens históricos concluídos sem evidência de regressão.
Legenda: `[x]` concluído, `[~]` parcial, `[ ]` pendente.

## Handoff obrigatório para a próxima IA

1. Executar `git status --short` e `git diff` antes de editar. Preservar qualquer alteração do
   usuário ou arquivo ainda não versionado; não usar reset/checkout para descartá-los.
2. Ler por inteiro `AUDITORIA_BIG_TECH_2026-08-01.md` e este checklist.
3. Trabalhar na ordem P0 → P1 → P2, preferencialmente um item ou conjunto atômico por PR/commit.
4. Antes de marcar `[x]`, registrar abaixo do item: arquivos alterados, migration/ADR quando houver,
   testes executados e resultado numérico.
5. Em auth, billing, organizations, audit, migrations e tenancy, exigir revisão independente antes
   do fechamento.
6. Não considerar “teste unitário verde” suficiente para concorrência ou SQL de produção: os itens
   correspondentes exigem PostgreSQL real.
7. Comandos mínimos no fechamento de cada lote:
   `.venv/Scripts/python.exe -m pytest -q`, `.venv/Scripts/python.exe -m mypy`,
   `.venv/Scripts/python.exe -m ruff check .`, `npm run type-check` e `npm run build`.

## Ciclo histórico — auditoria de 2026-07-16

Base histórica: `origin/main` em `c754f76`.

Validação registrada no fechamento: Ruff limpo, Mypy (135 arquivos) limpo, Pytest 233 passando.

Rastreia os itens do relatório `AUDITORIA_TECNICA_PROFUNDA_2026-07-16.md`, seções 11 e 12.

## Correções urgentes (P0 — 30 dias)

- [x] **Persistir falhas do Cloud Run Job diário, removendo rollback que apagava o ledger.**  
  `cloud_jobs.run_daily_pipeline` faz commit no sucesso e também no tratamento de exceção, de modo
  que o estado de falha marcado no ledger de execução persiste.
- [x] **Proteger `/operations/jobs` e `/operations/status`.**  
  Ambos exigem `Depends(require_operations_read)` em `operations/router.py`.
- [x] **Índices `devices(plant_id)`, `utility_bills(plant_id, status, cycle_end, created_at)` e
  `daily_energy_versions(daily_energy_id)`.**  
  Migration `20260716_0008_add_operational_scale_indexes.py`.

## Correções urgentes (P1 dentro da janela de 30 dias)

- [x] **Allowlist/validação de URLs externas em produção.**  
  `external_http_allowed_hosts` com validação por host em `core/config.py`.
- [x] **Request ID e middleware de logging.**  
  Contexto de correlação em `observability/context.py`, aplicado a logs estruturados e propagado
  ao tracing.

## Melhorias táticas (90 dias)

- [x] **RBAC/tenant/user para acesso por usina.**  
  Entregue como evolução em fases:
  papéis e escopo por usina (ADR-043), usuários nomeados com expiração e desativação em cascata
  (ADR-044). A dimensão de *tenant* foi conscientemente descartada por decisão de produto
  single-tenant (ADR-045); o modelo de autorização é considerado completo para o escopo atual.
- [x] **Remover `plant_id` nullable de faturas após migração de legado.**  
  Migration `20260716_0010_require_utility_bill_plant.py`: faz backfill quando existe exatamente
  uma planta, falha com mensagem operacional clara quando ambíguo, altera para `NOT NULL`.
  Modelo SQLAlchemy já reflete `nullable=False`. Item estava pendente apenas no checklist.
- [x] **Materializar snapshot mensal para dashboard/relatórios.**  
  Snapshot imutável de relatório mensal materializado em sessão anterior (PR #41).
  Cache/read-model do dashboard executivo concluído (ADR-049, sessão 2).
- [x] **Refatorar relatórios em contrato, projeção, renderizadores e estilos (P2).**  
  Paleta centralizada em `reports/export/theme.py`; renderizadores em
  `reports/export/pdf_renderer.py` e `reports/export/xlsx_renderer.py`. Fachadas
  `pdf_exporter.py` e `xlsx_exporter.py` mantêm assinatura pública inalterada.
  Validado com golden tests em `test_report_exporter_golden.py`.
- [x] **Métricas OpenTelemetry/Prometheus e alertas de SLO.**  
  Métricas de duração e resultado por operação exportadas ao Cloud Monitoring, com runbook de
  alertas de SLO (ADR-042).

## Melhorias estratégicas (6–12 meses)

- [x] **Migrar coleta/processamento para fila e workers.**  
  Fila de coleta no Postgres com claim atômico e backoff (ADR-046); camada de resiliência do
  provedor NEPViewer com retry e detecção de dados incompletos (ADR-047); job de coleta que defere
  para a fila em indisponibilidade persistente (PR #50); worker de drenagem que reprocessa os dias
  deferidos isolando cada tarefa em sua transação (PR #51).
- [x] **Particionamento/retention para séries temporais e ledgers.**  
  `TimeSeriesRetentionService` + `TimeSeriesRetentionWindows` em
  `retention/timeseries_service.py` purga `daily_energy` (por `production_date`) e
  `daily_climate_observations` (por `observation_date`) com janela padrão de 1825 dias
  (5 anos, exigência fiscal BR). `daily_energy_versions` excluído por CASCADE.
  Integrado em `run_retention()` na mesma transação. Coberto por `test_timeseries_retention.py`.
- [x] **Cache/read models para dashboards executivos (P2).**  
  Concluído (ADR-049): read-model com cache invalidado por impressão digital dos dados de energia
  do ciclo. Nunca serve resultado obsoleto — a impressão muda quando os dados mudam.
- [x] **Exportação assíncrona em lote com storage de artefatos (P2).**  
  Tabela `report_export_tasks` (migration 0018); `ArtifactStorage` Protocol +
  `InMemoryArtifactStorage`; `ReportExportService.enqueue/claim/complete/fail`;
  worker `drain_report_exports`; CLI `drain-report-exports`; endpoints
  `POST/GET /reports/monthly/exports` e `GET /reports/monthly/exports/{id}/download`.
  GCS configurável via `MPLACAS_REPORT_EXPORT_BUCKET` e `MPLACAS_REPORT_EXPORT_URL_TTL_SECONDS`.
  Coberto por `test_report_export_tasks.py`.
- [x] **Formalizar auditoria de ator e trilha de alterações.**  
  Trilha de auditoria persistente de ações sensíveis e administrativas (ADR-032, ADR-033, ADR-034),
  com o ator identificado por credencial. A dimensão de *tenants* não se aplica (ADR-045).

## Observabilidade (seção 7) — itens adicionais

- [x] Corrigir rollback do Cloud Run Job para persistir falhas no ledger.
- [x] Proteger `/operations/*`.
- [x] Adicionar request ID e logging middleware.
- [x] Tracing distribuído (ADR-041).
- [x] Métricas OpenTelemetry (ADR-042).
- [x] Alertas sobre SLOs, falhas repetidas e pipelines presos (runbook de SLO, ADR-042).

## Resumo do ciclo histórico de 2026-07-16

| Categoria | Concluídos | Parciais | Pendentes |
|---|---:|---:|---:|
| P0 (urgentes) | 3 | 0 | 0 |
| P1 (30 dias) | 2 | 0 | 0 |
| Táticas (90 dias) | 5 | 0 | 0 |
| Estratégicas (6–12m) | 5 | 0 | 0 |

**Todos os itens estão concluídos.** A tabela acima reflete o estado final: 15 itens entregues, 0
parciais, 0 pendentes. Inclui particionamento/retention (Frente 1), refatoração de relatórios
(Frente 2), exportação assíncrona em lote (Frente 3), cache de dashboard executivo, fila/workers,
RBAC single-tenant e `plant_id NOT NULL` em faturas.

---

## Ciclo BIG TECH — auditoria de 2026-08-01

Baseline de validação deste ciclo:

- Ruff aprovado;
- Mypy aprovado em 168 arquivos;
- frontend type-check e build aprovados;
- `pip check` aprovado;
- Pytest: **513 passaram, 3 falharam, 62 warnings**;
- `npm audit`: 4 vulnerabilidades high reportadas;
- `pip-audit`: 36 vulnerabilidades conhecidas em 2 pacotes;
- migration em SQLite vazio falhou em `CREATE TYPE datastatus`.

### P0 — bloqueadores de release

- [x] **P0-01 — atualizar `pypdf` para versão corrigida.**
  - Alterar a constraint para `pypdf>=6.14.2,<7` ou versão posterior comprovadamente corrigida.
  - Revisar breaking changes da major e adaptar `telegram/pdf.py`.
  - Critério de aceite: testes de PDF, Telegram e parser passando; `pip-audit` sem vulnerabilidade
    runtime conhecida aplicável ao `pypdf`.
  - Evidência esperada: versão resolvida registrada e resultado do scan anexado ao item.
  - Concluído em 2026-08-01: constraint `pypdf>=6.14.2,<7`, ambiente resolvido em `6.14.2`,
    testes do parser/Telegram aprovados e `pip-audit` retornou zero vulnerabilidades conhecidas.

- [x] **P0-02 — isolar parsing de PDF não confiável.**
  - Não executar `PdfReader`/`extract_text()` diretamente no event loop da API.
  - Usar processo/worker isolado com timeout de CPU, limite de memória e cancelamento observável.
  - Preservar limites de tamanho, páginas, texto extraído e rejeição de PDF criptografado.
  - Adicionar fixtures adversariais seguras para timeout, payload comprimido e extração excessiva.
  - Critério de aceite: falha do parser não bloqueia `/health`, não derruba o worker web e retorna
    erro controlado sem registrar conteúdo da fatura.
  - Concluído em 2026-08-01: processo descartável via `spawn`, timeout de parede, limites Linux de
    CPU/memória, cancelamento com `terminate/kill`, limites incrementais de texto/páginas e logs sem
    conteúdo. Fixtures cobrem criptografia, expansão comprimida, timeout e event loop responsivo.

- [x] **P0-03 — remover o dashboard legado que persiste chave operacional.**
  - Remover/redirecionar `/dashboard` e os assets legados, mantendo uma única SPA JWT.
  - Publicar limpeza de `localStorage.mplacas_creds_v1` para instalações existentes.
  - Atualizar `ADR-012`, README, auditoria histórica e `test_web_dashboard.py`.
  - Adicionar headers de segurança/CSP no frontend e na borda aplicável.
  - Critério de aceite: busca por `localStorage` não encontra persistência de credencial/chave/token;
    nenhum fluxo de usuário final solicita `X-API-Key` administrativo.
  - Concluído em 2026-08-01: assets FastAPI removidos, `/dashboard` responde `308` para a SPA JWT,
    frontend apenas remove a chave legada sem lê-la, ADR/README corrigidos e headers CSP/HSTS,
    anti-frame, `nosniff`, referrer e permissions policy publicados.
  - Hardening adicional em 2026-08-02: CSP restringido ao backend canônico, COOP/CORP publicados e
    cache imutável limitado aos assets Vite com hash. O workflow Cloudflare
    [30774178800](https://github.com/welitonsp/mplacas/actions/runs/30774178800) foi aprovado; HTML
    permaneceu com revalidação e a borda real confirmou todos os headers.

- [x] **P0-04 — rotacionar credenciais potencialmente persistidas pelo dashboard.**
  - Confirmar em logs/métricas se a página legada foi usada em produção.
  - Rotacionar `MPLACAS_OPERATIONS_API_KEY` e chaves READ potencialmente expostas.
  - Validar que consumidores legítimos migraram para JWT ou credencial persistida escopada.
  - Critério de aceite: evidência operacional sem registrar o segredo; plano de rollback documentado.
  - Concluído em 2026-08-02: inventário somente leitura encontrou zero acessos a `/dashboard` e
    zero chamadas a `/operations/*` em 90 dias. Somente a service account `mplacas-runtime` possui
    `secretAccessor`; API e 11 jobs eram os consumidores configurados e não existe chave READ
    separada. A versão 2 foi criada sem exposição e ativada na revisão
    `mplacas-api-00013-5g6`, com 100% do tráfego. `/health`, `/ready` e autenticação nova retornaram
    200, enquanto a chave anterior retornou 401. `mplacas-smoke-hq4xr` e
    `mplacas-operational-watchdog-pm2j5` concluíram com sucesso. Após a janela de validação, a
    versão 1 foi desativada de forma reversível e a versão 2 permaneceu como a única habilitada.
    O deploy padrão subsequente passou pelo preflight de versão única, publicou
    `mplacas-api-00014-f9p` com 100% do tráfego e confirmou `/health` e `/ready` com HTTP 200;
    `mplacas-smoke-9x4bn` e `mplacas-operational-watchdog-pwqv8` também foram aprovados. O
    procedimento repetível está em `infra/gcp/rotate-operations-key.sh` e no
    `RUNBOOK_ROTACAO_CREDENCIAL_OPERACIONAL.md`.
    Validação: 18 testes do contrato GCP e suíte global com **609 passed**, **4 skipped**;
    Mypy aprovado em 180 arquivos, Ruff limpo, frontend type-check e build aprovados.

- [x] **P0-05 — restaurar baseline de testes totalmente verde.**
  - Corrigir o drift de `.dockerignore`, `.gcloudignore` e `infra/gcp/lib.sh`/respectivo contrato.
  - Garantir exclusão de `storage/`, `backups/`, `reports/`, bancos, dumps, PDFs e secrets do contexto
    enviado ao Cloud Build.
  - Tratar warnings de threads `aiosqlite`/event loop como vazamento de recurso, não apenas silenciá-los.
  - Critério de aceite: zero testes falhando e ausência de `PytestUnhandledThreadExceptionWarning`.
  - Concluído em 2026-08-01: contratos de ignore/deploy alinhados, conexões SQLite descartadas de
    forma determinística e CI promovido para falhar nesse warning. Evidência: **522 passed**, sem
    `PytestUnhandledThreadExceptionWarning`; Ruff e Mypy aprovados.
  - Reaberto em 2026-08-02 por evidência de regressão intermitente: a suíte funcional completa passava,
    mas o modo estrito encontrou workers `aiosqlite` após fechamento do event loop. A causa estava em
    helpers de teste que devolviam apenas o `sessionmaker`, perdiam a referência do engine e não
    executavam `dispose()`, além de instâncias de `TestClient` sem fechamento explícito.
  - Reestabilizado em 2026-08-02: fixtures passaram a manter ownership explícito dos engines e clients,
    fechar `TestClient` e descartar engines ao término de cada teste. Evidência: lote crítico com
    **118 passed** em modo estrito; suíte global com **579 passed**, **2 skipped** e zero
    `PytestUnhandledThreadExceptionWarning`; Ruff aprovado, Mypy aprovado em 176 arquivos e Alembic
    com head único `20260802_0034`.

- [x] **P0-06 — incorporar segurança de dependências ao CI.**
  - Executar `pip-audit`, `npm audit`, scan da imagem e geração de SBOM.
  - Atualizar React Router/Wrangler e classificar advisories não aplicáveis com justificativa
    versionada e prazo de revisão; não usar exclusão genérica.
  - Critério de aceite: CI bloqueia vulnerabilidade runtime high/critical aplicável e publica os
    relatórios como artifacts.
  - Implementado em 2026-08-01: `pip-audit` e `npm audit` bloqueantes com artifacts, SBOM CycloneDX e
    Trivy high/critical adicionados ao workflow. React Router, Wrangler, pytest e pytest-asyncio
    atualizados; scans locais Python e Node retornaram zero vulnerabilidades.
  - Concluído em 2026-08-02: a execução remota
    [CI 30753841013](https://github.com/welitonsp/mplacas/actions/runs/30753841013) aprovou os cinco
    jobs e publicou `pip-audit-report` (artifact 8835306601), `npm-audit-report` (8835300272),
    `container-sbom` (8835306852) e `trivy-results` (8835309543). A execução
    [Security 30753841032](https://github.com/welitonsp/mplacas/actions/runs/30753841032) aprovou
    CodeQL e Gitleaks, com SARIF do Gitleaks no artifact 8835299439.

### P1 — segurança, banco e operação

- [x] **P1-01 — tornar refresh-token rotation atômica e detectar replay.**
  - Implementar compare-and-swap/`UPDATE ... WHERE active=true RETURNING` ou lock equivalente.
  - Definir família de sessão e revogá-la ao detectar reutilização.
  - Adicionar teste concorrente em PostgreSQL com duas rotações simultâneas do mesmo token.
  - Critério de aceite: exatamente uma rotação vence; nenhuma sessão órfã permanece ativa.
  - Implementado em 2026-08-01: rotação convertida para compare-and-swap atômico com `RETURNING`,
    família persistida por migration e revogação da família inteira em replay. Testes locais de
    contrato e replay passaram.
  - Concluído em 2026-08-02: o job
    [postgres-integration](https://github.com/welitonsp/mplacas/actions/runs/30753841013/job/91512481640)
    executou duas rotações simultâneas no PostgreSQL 16 e comprovou exatamente um vencedor, com
    revogação integral da família após replay. Relatório preservado no artifact
    `postgres-integration-report` 8835307257 por 30 dias.

- [x] **P1-02 — endurecer contrato JWT.**
  - Fixar allowlist de algoritmo; exigir segredo com no mínimo 32 bytes; adicionar `aud`.
  - Definir estratégia de rotação/versionamento de chave.
  - Revisar validação de usuário/organização/role para ações ADMIN.
  - **Decisão necessária:** a janela residual de 15 minutos foi aceita no checklist SaaS de
    2026-07-31. Não alterar silenciosamente; registrar ADR se a postura para incidentes mudar.
  - Critério de aceite: testes de algoritmo/issuer/audience/secret/role e comportamento pós-revogação.
  - Concluído em 2026-08-01: HS256 fixo, segredo mínimo de 32 bytes, `iss`/`aud`/`kid`
    obrigatórios, rollover explícito para uma chave anterior e validação estrita de role/`jti`.
    A janela residual aceita foi preservada e documentada no ADR-052; testes cobrem algoritmo,
    audiência, chave, segredo, role e rollover.

- [x] **P1-03 — fazer ausência de execução degradar o SLO.**
  - Adicionar heartbeat/freshness, janela esperada e mínimo de execuções.
  - Distinguir “sem histórico”, “atrasado”, “preso”, “falhou” e “saudável”.
  - Critério de aceite: Scheduler ausente/parado nunca resulta em `healthy`.
  - Concluído em 2026-08-01: estado, freshness, grace period e volume mínimo foram incorporados
    ao cálculo e ao status operacional. Ausência de histórico, atraso, execução presa, falha e
    histórico insuficiente degradam explicitamente o serviço e emitem códigos de alerta testados.

- [x] **P1-04 — criar pipeline de integração PostgreSQL/migrations no CI.**
  - Executar `alembic upgrade head` em banco PostgreSQL vazio e `alembic check`.
  - Testar locks/`SKIP LOCKED`, outbox, filas e refresh concorrente.
  - Corrigir a promessa de migrations SQLite ou torná-las portáveis conscientemente.
  - Critério de aceite: schema criado apenas por migrations atende `/ready` e testes de integração.
  - Parcial em 2026-08-01: job PostgreSQL 16 adiciona `alembic upgrade head`, `alembic check` e
    teste de concorrência real da rotação. O metadata de migrations passou a importar os modelos
    de autenticação.
  - Ampliado em 2026-08-02: testes PostgreSQL agora mantêm locks reais em dois workers e comprovam
    `SKIP LOCKED` para fila de coleta e outbox, verificam `alembic_version`/tabelas criadas somente por
    migrations e exercitam `/ready` contra o banco migrado. O job falha em warning de thread e publica
    `postgres-integration-report` por 30 dias; runbook registra execução local segura e evidência de
    aceite. Contratos locais passaram e a suíte global encerrou com **597 passed**, **4 skipped** — os
    dois novos skips são explicitamente PostgreSQL por ausência de `MPLACAS_TEST_POSTGRES_URL` — e zero
    `PytestUnhandledThreadExceptionWarning`; Ruff e Mypy aprovados em 181 arquivos.
  - Concluído em 2026-08-02: após alinhar constraints/índices do metadata e aplicar a migration
    `20260802_0037_enforce_auth_timestamp_not_null.py`, o job remoto
    [postgres-integration](https://github.com/welitonsp/mplacas/actions/runs/30753841013/job/91512481640)
    aprovou `alembic upgrade head`, `alembic check`, schema na revisão `20260802_0037`, refresh
    concorrente, locks/`SKIP LOCKED`, fila, outbox, `/ready` e PoC de RLS. Artifact auditável:
    `postgres-integration-report` 8835307257, retenção de 30 dias.

- [~] **P1-05 — automatizar componentes operacionais obrigatórios.**
  - Provisionar Cloud Run Jobs, Scheduler, IAM mínimo, policies de alerta e verificação pós-deploy.
  - Cobrir collect, daily-pipeline, drains, outbox, relatórios e retenção.
  - Critério de aceite: deploy idempotente detecta componente ausente e smoke test confirma execução.
  - Parcial em 2026-08-01: provisionador idempotente passou a cobrir coleta, pipeline, outbox,
    drains de coleta/relatórios, digest e retenção, com Scheduler e identidade invocadora dedicada.
  - Ampliado em 2026-08-02: watchdog horário somente leitura valida o ledger do pipeline em modo
    fail-closed (sem histórico, falha, stuck e atraso acima de 26h). Duas policies versionadas usam a
    métrica nativa de Cloud Run Jobs para detectar resultado sem sucesso e ausência do watchdog por
    duas horas. O provisionador cria/atualiza por identidade estável, rejeita duplicatas e exige canal
    completo do mesmo projeto; o verificador exige jobs existentes, schedules `ENABLED`, policies
    habilitadas/canalizadas e sucesso de smoke + watchdog. Runbook/ADR registram ativação, incidente
    controlado e rollback. Contratos direcionados passaram (**33 passed**), a suíte global encerrou
    com **604 passed**, **4 skipped**, Ruff aprovou todo o repositório, Mypy aprovou 181 arquivos e
    `bash -n` aprovou todos os scripts GCP. ShellCheck permanece coberto no CI, pois o binário não está
    instalado nesta estação.
  - Falta executar provisionamento/verificação no projeto GCP, anexar IDs/execuções sem segredos e
    comprovar em homologação a abertura e o fechamento do incidente de ausência. A checagem segura
    desta estação confirmou `gcloud` autenticado e projeto/região configurados, mas bloqueou a
    execução porque `GCP_MONITORING_NOTIFICATION_CHANNELS`, `MPLACAS_CLOUD_JOB_PLANT_NAME` e
    `MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH` ainda estão vazios em `config.env`.
  - Evidência adicional em 2026-08-02: o job remoto
    [gcp-deployment-contract](https://github.com/welitonsp/mplacas/actions/runs/30753841013/job/91512481601)
    aprovou sintaxe Bash, ShellCheck e contratos do provisionador. Isso valida o artefato de deploy,
    mas não substitui o provisionamento e o incidente controlado no projeto GCP.
  - Provisionado e verificado no projeto `mplacas`, região `us-central1`, em 2026-08-02. A revisão
    `mplacas-api-00011-h5w` serve 100% do tráfego com a imagem digest `sha256:face3830...789072`;
    `/health` e `/ready` responderam `200`. A migration executou com sucesso em
    `mplacas-migrate-88n8r`. Oito jobs e oito schedules canônicos ficaram habilitados, ligados à
    identidade `mplacas-scheduler`; o trigger legado duplicado `mplacas-daily-digest-schedule` foi
    pausado de forma reversível. As policies `10276572730635623905` (falha) e
    `5164561916173011069` (ausência) estão habilitadas no canal
    `8771600232734038494`.
  - A ativação real criou histórico por `mplacas-collect-wbjcf` e
    `mplacas-daily-pipeline-hx85l`; depois, `mplacas-smoke-2vr7t` e
    `mplacas-operational-watchdog-wzw87` concluíram com sucesso. A primeira tentativa do watchdog
    falhou corretamente com `daily pipeline has no execution history`, comprovando comportamento
    fail-closed antes da inicialização do ledger. O PR
    [#78](https://github.com/welitonsp/mplacas/pull/78) corrigiu o contexto de source deploy que
    excluía `src/mplacas/reports` e foi integrado após todos os checks verdes.
  - Permanece parcial somente porque o teste de abertura/entrega/fechamento após duas horas deve ser
    feito em homologação. Não pausar o watchdog de produção para produzir essa evidência.

- [~] **P1-06 — automatizar backup/PITR e restore drill.**
  - Definir RPO/RTO, retenção, criptografia, ownership e alerta de falha.
  - Restaurar periodicamente em banco descartável, aplicar migrations e validar `/ready`/invariantes.
  - Critério de aceite: último restore drill aprovado e auditável, não apenas backup existente.
  - Parcial em 2026-08-02: workflow diário versionado gera snapshot lógico criptografado com
    retenção de 35 dias, restaura apenas em hostname descartável confirmado, aplica migrations,
    valida invariantes e `/ready`, publica manifest e abre incidente deduplicado em falha. RPO de
    24h, RTO de 4h e ownership estão documentados. O environment protegido
    `production-restore-drill` foi configurado com secrets e owner; o destino é PostgreSQL 18
    efêmero, isolado no runner, e a imagem oficial está fixada por digest. Os PRs
    [#80](https://github.com/welitonsp/mplacas/pull/80),
    [#82](https://github.com/welitonsp/mplacas/pull/82),
    [#83](https://github.com/welitonsp/mplacas/pull/83),
    [#84](https://github.com/welitonsp/mplacas/pull/84),
    [#85](https://github.com/welitonsp/mplacas/pull/85),
    [#86](https://github.com/welitonsp/mplacas/pull/86) e
    [#87](https://github.com/welitonsp/mplacas/pull/87) endureceram isolamento, DSNs, versões,
    supply chain, TLS e conexões explícitas.
  - Evidência operacional: a execução
    [#30765972320](https://github.com/welitonsp/mplacas/actions/runs/30765972320), no commit
    `b7b167b7716667a548fcdcdf075e0e4a316408fd`, foi aprovada em 2026-08-02. O artifact
    `8838949236` (`restore-drill-30765972320`) fica retido até 2026-09-06 e contém dump cifrado e
    manifest auditável: `pg_restore=passed`, `migrations=passed`, `critical_invariants=passed`,
    `ready_endpoint=passed`, `decision=approved`. O incidente deduplicado
    [#81](https://github.com/welitonsp/mplacas/issues/81) foi encerrado com essa evidência.
  - Manutenção operacional em 2026-08-02: a conexão direta foi saneada e, após rotação do
    `neondb_owner`, `mplacas-migration-database-url@3` ficou como única versão habilitada.
    `mplacas-migrate-5rpnl`, `mplacas-migrate-d6h9r` e `mplacas-migrate-9x5ht` concluíram com
    sucesso. A migration `20260802_0038` criou três índices de FK; auditoria posterior confirmou
    os três válidos, zero índices inválidos e nenhuma FK restante sem índice. Essa evidência
    confirma credencial e schema, mas não comprova nem altera a retenção PITR contratada no Neon.
    Implementação e CI PostgreSQL no PR
    [#91](https://github.com/welitonsp/mplacas/pull/91).
  - Permanece parcial somente até confirmar e registrar a janela PITR efetiva do plano Neon
    contratado; não reabrir a automação do restore drill sem evidência de regressão.

- [x] **P1-07 — adicionar retenção de autenticação e convites.**
  - Cobrir `auth_sessions`, `login_rate_limits` e `user_invitations` expirados/terminais.
  - Preservar evidência pelo período definido e não remover sessões ainda válidas.
  - Critério de aceite: serviço idempotente, métricas por tabela e testes de boundary temporal.
  - Concluído em 2026-08-01: janelas configuráveis cobrem sessões, rate limits e convites;
    registros válidos/bloqueios ativos são preservados, resultados são contabilizados por tabela
    e testes confirmam limites temporais e idempotência.

### P2 — arquitetura, tenancy e supply chain

- [~] **P2-01 — elaborar ADR e prova de conceito de PostgreSQL RLS.**
  - Usar tenant context transacional, política fail-closed e bypass explícito apenas para plataforma.
  - Critério de aceite: query sem tenant não retorna dados; teste cross-tenant direto no banco.
  - Parcial em 2026-08-01: ADR-056 define contrato e gates; helper usa `set_config(..., true)`
    transacional e limpa bypass ao vincular tenant. A prova PostgreSQL real demonstra zero linhas
    sem contexto, bloqueio de leitura/escrita cross-tenant e bypass que exige configuração explícita
    mais membership em role de plataforma. A PoC foi aprovada no job PostgreSQL remoto da execução
    [CI 30753841013](https://github.com/welitonsp/mplacas/actions/runs/30753841013).
  - Avanço produtivo em 2026-08-02: roles separadas. A revisão `mplacas-api-00016-wm8` usa
    `mplacas_runtime`, sem ownership ou `BYPASSRLS`, com timeouts defensivos; `neondb_owner` ficou
    restrito à conexão direta de migrations e teve a senha rotacionada. `/health`, `/ready`,
    `mplacas-smoke-4fz8w` e `mplacas-operational-watchdog-94tls` foram aprovados. Falta
    criar policies nas tabelas reais e validar o rollout/rollback em branch Neon descartável antes
    de ativar RLS em produção.
  - Fundação de rollout concluída em 2026-08-02: inventário executável classifica as **24 tabelas**
    ORM por ownership direto, planta, dispositivo, energia diária ou plataforma e é comparado com
    todo `Base.metadata` na CI. Todos os consumidores diretos de `SessionFactory()` na aplicação
    agora definem tenant ou plataforma como primeira operação; um teste AST impede novas sessões
    sem contexto. Rotas de tenant usam o principal autenticado, webhook Telegram troca descoberta
    global por tenant resolvido e workers globais declaram bypass de plataforma. RLS continua
    desativado. Restam modelar tenant em `audit_events`, criar/testar policies reais, autorizar a
    role de plataforma mínima e executar canário/rollback em branch Neon descartável. Validação
    consolidada: **626 passed**, **4 skipped**, Ruff e Mypy aprovados.
  - Evidência produtiva em 2026-08-02: o
    [PR #93](https://github.com/welitonsp/mplacas/pull/93) foi aprovado pelos jobs de qualidade,
    integração PostgreSQL, contrato GCP, frontend, container, CodeQL e secret scan. O commit
    `92d1f4a` foi implantado na revisão `mplacas-api-00017-vst`, com 100% do tráfego; `/health` e
    `/ready` retornaram HTTP 200, `mplacas-smoke-pdtvp` e
    `mplacas-operational-watchdog-xqndh` concluíram. A inspeção Neon confirmou
    `mplacas_runtime` sem superuser, `CREATEDB`, `CREATEROLE` ou `BYPASSRLS`, nenhuma tabela com
    RLS habilitado/forçado e ausência intencional da futura role `mplacas_platform`.
  - Policies e canário concluídos em 2026-08-02, sem ativação produtiva: migrations 0039/0040
    adicionam tenant nullable à auditoria, escopo/deduplicação de alertas por planta e policies
    fail-closed `USING`/`WITH CHECK` com
    `ENABLE/FORCE` nas 24 tabelas. O canário Neon descartável `a051b1a5` aprovou catálogo 24/24/2,
    CRUD cross-tenant, rollback para 0/0/0, re-upgrade para 24/24/2 e repetição dos testes; database
    e roles efêmeras foram removidos. A migration exige aprovação literal por variável, impedindo
    execução produtiva acidental. O listener transacional reaplica o contexto após `commit()` em
    sessões reutilizadas. Validação local: **630 passed**, **5 skipped**, Ruff e Mypy
    aprovados. O item permanece parcial somente até criar/conceder a role `mplacas_platform`, abrir
    janela produtiva, executar a 0040 e aprovar smoke/watchdog conforme `RUNBOOK_RLS_ROLLOUT.md`.

- [x] **P2-02 — escopar idempotência de faturas por usina/tenant.**
  - Substituir unicidade global de `source_hash` por constraint composta apropriada.
  - Criar migration segura, incluindo análise de duplicatas existentes e rollback.
  - Critério de aceite: o mesmo conteúdo pode existir em usinas diferentes sem colisão.
  - Parcial em 2026-08-01: ORM e repositório usam unicidade composta
    `(plant_id, source_hash)`; a consulta idempotente inclui a usina e a inserção concorrente usa
    savepoint para recuperar o vencedor sem abortar a transação externa. A migration 0031 analisa
    duplicatas antes do upgrade e bloqueia downgrade inseguro quando hashes cross-plant já existem.
    Testes locais comprovam reuso na mesma usina e coexistência em usinas distintas.
  - Concluído em 2026-08-02: `alembic upgrade head` e `alembic check` foram aprovados sobre banco
    PostgreSQL 16 vazio no job
    [postgres-integration](https://github.com/welitonsp/mplacas/actions/runs/30753841013/job/91512481640),
    incluindo a migration 0031 e todas as revisões posteriores. O PR
    [#91](https://github.com/welitonsp/mplacas/pull/91) avançou o head para 0038 e repetiu o gate
    PostgreSQL real com sucesso.

- [x] **P2-03 — tornar builds Python reproduzíveis e reforçar supply chain.**
  - Adotar lock com hashes, pin de imagem por digest e Actions por SHA.
  - Adicionar atualização automatizada, secret scan, SAST e política de proveniência/SBOM.
  - Critério de aceite: rebuild da mesma revisão resolve as mesmas dependências verificadas.
  - Parcial em 2026-08-02: locks separados runtime/dev fixam dependências transitivas com hashes;
    Docker usa base Python por digest e instala com `--require-hashes`; Actions foram fixadas por
    commit e PostgreSQL por digest. Dependabot, CodeQL, Gitleaks e attestation de proveniência foram
    versionados, preservando SBOM/Trivy/auditorias existentes. Instalação seca dos locks e contratos
    locais passaram. Linux/Python 3.12, build por digest, SBOM, Trivy, CodeQL e Gitleaks foram
    aprovados nas execuções remotas 30753841013 e 30753841032.
  - Concluído em 2026-08-02: após o merge do PR #68, a execução
    [CI 30754471086](https://github.com/welitonsp/mplacas/actions/runs/30754471086) em `main` aprovou
    novamente os cinco jobs e publicou a
    [attestation 38431381](https://github.com/welitonsp/mplacas/attestations/38431381), assinada via
    Sigstore e registrada no Rekor para `mplacas-image.tar` com digest
    `sha256:0fd6b604fe68eb6bf1e20e577026a06c8286aca5bbe3c77a31c3cf83d3c4390a`.

- [x] **P2-04 — consolidar frontend e documentação.**
  - Remover contratos conflitantes entre dashboard FastAPI e SPA Cloudflare.
  - Corrigir ADR-012, ADR-052, README, auditoria de 2026-07-16 e testes.
  - Critério de aceite: uma única política documentada para tokens, logout, refresh e headers.
  - Concluído em 2026-08-02: `AUTH_FRONTEND_CONTRACT.md` tornou-se a fonte canônica para SPA,
    tokens somente em memória, refresh rotativo, logout, redirecionamento e headers. Logout agora
    limpa o cliente imediatamente e revoga a sessão persistida por endpoint idempotente `204`.
    ADRs/runbooks/auditoria foram alinhados, wildcard CORS documental removido e testes impedem
    persistência de tokens, retorno do dashboard legado e divergência dos headers Cloudflare.

- [x] **P2-05 — refatorar `alerts/production_alert.py` após estabilização funcional.**
  - Separar coleta/read model, decisão pura, apresentação e despacho.
  - Eliminar N+1 por dispositivo na construção de medianas.
  - Preservar golden tests e fingerprints para não reenviar/suprimir alertas indevidamente.
  - Concluído em 2026-08-02: o fluxo mantém etapas explícitas de coleta, decisão pura e
    apresentação, enquanto o novo `production_alert_dispatch.py` isola provider, ledger e a ordem
    de confirmação at-most-once. As medianas dos inversores agora usam uma consulta agregada de
    energia e uma série climática compartilhada, em vez de duas consultas por dispositivo. Um teste
    com oito inversores limita a coleta completa a nove `SELECTs`, independentemente do tamanho da
    frota. Os 29 testes do alerta, inclusive os casos golden, fingerprints, escalonamento e dedup,
    passaram; a regressão completa encerrou com 549 testes aprovados e 2 ignorados.

### P2/P3 — evolução do motor fotovoltaico

- [x] **SOL-01 — modelar configuração técnica da usina.**
  Potência DC/AC, potência por inversor, inclinação, azimute, tecnologia e comissionamento.
  - Concluído em 2026-08-02: `Plant` preserva `installed_power_kwp` como potência DC total e passa
    a registrar potência AC, inclinação, azimute, tecnologia do módulo e data de comissionamento;
    `Device` registra potências DC e AC por inversor. A migration 0032 adiciona colunas anuláveis
    para rollout gradual, preflight de dados legados e `CHECK constraints` físicos. Endpoints GET e
    PATCH tenant-safe atualizam usina/inversores atomicamente, exigem READ/ADMIN e registram auditoria.
    O ADR-057 fixa unidades, convenção de azimute e limites do modelo agregado. Evidência local:
    Alembic com head único 0032, Ruff aprovado, Mypy aprovado em 170 arquivos e suíte completa com
    558 testes aprovados e 2 ignorados.
- [x] **SOL-02 — implementar irradiância POA e correção térmica.**
  Não chamar GHI horizontal de Performance Ratio; usar fonte/modelo e versão explícitos.
  - Concluído em 2026-08-02: o motor puro `MPLACAS_POA_DAILY_ERBS_ISOTROPIC_V1` decompõe GHI
    diário por Erbs, integra a componente direta conforme geometria solar, transpõe céu difuso
    isotrópico e estima temperatura de célula/correção térmica simplificada por NOCT e tecnologia.
    A migration 0033 persiste resultados por usina/data/fonte/versão com snapshots das entradas,
    premissas e flags de qualidade. A coleta climática atualiza projeções idempotentemente na mesma
    transação; configuração ou temperatura ausente permanece explícita, sem valores inventados.
    Métricas do endpoint/pipeline e retenção cobrem a nova série. ADR-058 documenta fórmulas,
    referências e limitações, sem denominar o resultado como Performance Ratio. Evidência local:
    Alembic com head único 0033, Ruff aprovado, Mypy aprovado em 174 arquivos e suíte estrita contra
    warnings de thread com 568 testes aprovados e 2 ignorados.
- [x] **SOL-03 — implementar PR e disponibilidade alinhados à IEC 61724-1.**
  Persistir premissas, versão, unidade, natureza e incerteza.
  - Concluído em 2026-08-02: `MPLACAS_IEC61724_DAILY_PR_V1` calcula yield final, yield de referência,
    PR AC diário e PR corrigido por temperatura separadamente. O indicador de disponibilidade é
    explicitamente `CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY`, nunca disponibilidade técnica sem
    telemetria intervalar. A migration 0034 persiste fonte, versões, unidades, natureza, premissas,
    qualidade e incerteza não quantificada com motivo. O pipeline executa POA → PR → alertas,
    idempotentemente, e a retenção cobre a nova série. ADR-059 documenta alinhamento e limites frente
    à IEC 61724-1 e IEC TS 63019. Evidência: Alembic head único 0034, Ruff aprovado, Mypy aprovado em
    176 arquivos, 37 testes da frente aprovados em modo estrito e suíte funcional completa com
    579 aprovados e 2 ignorados.
- [x] **SOL-04 — baseline sazonal robusta e degradação de longo prazo.**
  Usar clear-sky index, MAD/quantis e comparação sazonal; impedir baseline contamination.
  - Concluído em 2026-08-02: `MPLACAS_SEASONAL_PR_BASELINE_V1` congela a referência nos
    primeiros 366 dias elegíveis, separa estações por mês civil e nunca usa observações futuras.
    Dados provisórios, disponibilidade reportada abaixo de 95%, baixa irradiância e PR fora da faixa
    admissível são excluídos. A envoltória empírica de céu limpo usa P90 sazonal de POA; mediana,
    MAD escalada e quantis removem outliers sem permitir que degradação posterior seja reaprendida
    como normal.
  - A comparação exige 12 amostras robustas de referência e 7 posteriores, persiste baseline,
    dispersão, limites, índice de céu limpo, degradação absoluta/anualizada, classificação e premissas
    em snapshot versionado/idempotente. O pipeline passou a executar POA → PR → baseline sazonal →
    alertas; retenção e resposta operacional cobrem a nova série. ADR-060 registra decisões e limites.
    Evidência: Alembic head único `20260802_0035`, Ruff aprovado, Mypy aprovado em 178 arquivos,
    34 testes da frente aprovados em modo estrito e suíte global com **585 passed**, **2 skipped** e
    zero `PytestUnhandledThreadExceptionWarning`.
- [x] **SOL-05 — taxonomia técnica de perdas.**
  Diferenciar comunicação, indisponibilidade, clipping, sujeira, sombra, temperatura e degradação.
  - Concluído em 2026-08-02: `MPLACAS_DAILY_LOSS_TAXONOMY_V1` avalia separadamente comunicação,
    indisponibilidade, clipping, sujeira, sombra, temperatura, degradação e perda não explicada.
    Cada categoria persiste nível `LIKELY`, `POSSIBLE`, `NOT_DETECTED` ou `NOT_ASSESSABLE`, códigos
    de evidência, limitação e estimativa somente quando defensável.
  - Falha de reporte não é rotulada como indisponibilidade técnica; energia zero com reporte completo
    e POA material gera indício de indisponibilidade. Clipping e sujeira permanecem hipóteses quando
    suportados por razão DC/AC, índice de céu limpo, período seco e shortfall. Sombra fica explicitamente
    não avaliável sem potência intervalar; temperatura usa a diferença entre PR padrão/corrigido e
    degradação consome exclusivamente a baseline congelada da SOL-04.
  - A persistência cria uma linha versionada por planta/dia/categoria, inclusive para categorias não
    avaliáveis. Pipeline e retenção cobrem a nova série; ADR-061 registra limites e dados necessários
    para elevar confiança. Evidência: Alembic head único `20260802_0036`, Ruff aprovado, Mypy aprovado
    em 180 arquivos, 35 testes da frente aprovados em modo estrito e suíte global com **591 passed**,
    **2 skipped** e zero `PytestUnhandledThreadExceptionWarning`.
- [~] **SOL-06 — datasets golden validados por especialista.**
  Casos reais anonimizados, labels revisados e métricas de falso positivo/falso negativo.
  - Parcial em 2026-08-02: o contrato `MPLACAS_SOLAR_GOLDEN_V1` diferencia casos sintéticos de
    casos de campo anonimizados, exige labels para todas as categorias e registra revisão `PENDING` ou
    `APPROVED` com papel, data e referência de evidência. O carregador rejeita campos identificadores
    em qualquer profundidade e impede promover caso sintético como evidência aprovada.
  - O avaliador calcula TP, FP, FN, TN, abstenção, cobertura, precisão, recall, FPR e FNR por categoria.
    O gate exige revisão especialista, ao menos 5 positivos/5 negativos por categoria, precisão/recall
    mínimas de 80%, cobertura mínima de 90% e FPR/FNR máximas de 20%. Datasets aprovados futuros entram
    automaticamente no gate da suíte. CLI e runbook permitem execução e continuidade por outra IA.
  - O candidato versionado atual contém 4 cenários sintéticos e protege regressões determinísticas,
    mas retorna corretamente `release_gate_passed=false`: não existem no repositório casos reais
    anonimizados nem evidência de revisão por especialista. ADR-062 proíbe considerar essa fixture como
    validação científica. Evidência técnica: Ruff aprovado, Mypy aprovado em 181 arquivos, 5 testes da
    frente aprovados e suíte global com **596 passed**, **2 skipped** e zero
    `PytestUnhandledThreadExceptionWarning`; Alembic permanece no head único `20260802_0036`.
  - Para concluir: obter amostra de campo autorizada, anonimizar fora do Git, revisar labels com
    especialista solar, registrar referência controlada e fazer o gate balanceado passar sem reduzir
    thresholds. Procedimento completo em `RUNBOOK_VALIDACAO_GOLDEN_SOLAR.md`.

## Resumo do ciclo BIG TECH de 2026-08-01

| Categoria | Concluídos | Parciais | Pendentes |
|---|---:|---:|---:|
| P0 | 6 | 0 | 0 |
| P1 | 5 | 2 | 0 |
| P2 arquitetura/supply chain | 4 | 1 | 0 |
| Evolução solar | 5 | 1 | 0 |
| **Total novo** | **20** | **4** | **0** |

Próxima ação recomendada: preparar uma homologação isolada para o incidente controlado de ausência
de **P1-05** e confirmar/documentar a janela PITR efetiva do plano Neon para fechar **P1-06**.
Na implementação local, a próxima ação é concluir **SOL-06** com dados de campo autorizados e revisão
real de especialista, seguindo `RUNBOOK_VALIDACAO_GOLDEN_SOLAR.md`. O fechamento de **P2-01** permanece
condicionado ao rollout de RLS.
