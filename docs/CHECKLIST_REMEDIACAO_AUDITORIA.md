# Checklist de remediação — Auditoria técnica profunda (2026-07-16)

Última atualização: 2026-07-20  
Base: `origin/main` em `c754f76`  
Validação local no fechamento: Ruff limpo, Mypy (135 arquivos) limpo, Pytest 233 passando.

Rastreia cada item do roadmap da auditoria (`AUDITORIA_TECNICA_PROFUNDA_2026-07-16.md`,
seções 11 e 12) ao seu estado atual, com a evidência correspondente. Legenda:
`[x]` concluído, `[~]` parcial, `[ ]` pendente.

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
- [~] **Materializar snapshot mensal para dashboard/relatórios.**  
  Snapshot imutável de relatório mensal já materializado em sessão anterior (PR #41). O
  cache/read-model do dashboard executivo permanece pendente (ver P2 estratégico).
- [ ] **Refatorar relatórios em contrato, projeção, renderizadores e estilos (P2).**  
  Pendente. `xlsx_exporter.py`, `reports/service.py` e `pdf_exporter.py` seguem grandes.
- [x] **Métricas OpenTelemetry/Prometheus e alertas de SLO.**  
  Métricas de duração e resultado por operação exportadas ao Cloud Monitoring, com runbook de
  alertas de SLO (ADR-042).

## Melhorias estratégicas (6–12 meses)

- [x] **Migrar coleta/processamento para fila e workers.**  
  Fila de coleta no Postgres com claim atômico e backoff (ADR-046); camada de resiliência do
  provedor NEPViewer com retry e detecção de dados incompletos (ADR-047); job de coleta que defere
  para a fila em indisponibilidade persistente (PR #50); worker de drenagem que reprocessa os dias
  deferidos isolando cada tarefa em sua transação (PR #51).
- [ ] **Particionamento/retention para séries temporais e ledgers.**  
  Pendente. Próxima P1 natural: política de retenção para `job_runs`, `pipeline_executions`,
  `alert_delivery_records` e avaliação de particionamento para `daily_energy` e clima.
- [x] **Cache/read models para dashboards executivos (P2).**  
  Concluído (ADR-049): read-model com cache invalidado por impressão digital dos dados de energia
  do ciclo. Nunca serve resultado obsoleto — a impressão muda quando os dados mudam.
- [ ] **Exportação assíncrona em lote com storage de artefatos (P2).**  
  Pendente. Exportadores PDF/XLSX ainda geram em memória.
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

## Resumo

| Categoria | Concluídos | Parciais | Pendentes |
|---|---:|---:|---:|
| P0 (urgentes) | 3 | 0 | 0 |
| P1 (30 dias) | 2 | 0 | 0 |
| Táticas (90 dias) | 3 | 1 | 1 |
| Estratégicas (6–12m) | 2 | 0 | 3 |

Todos os itens **P0** e **P1 de curto prazo** estão concluídos. Entre as melhorias de maior
horizonte, a fila/workers, o RBAC (com decisão single-tenant) e o `plant_id NOT NULL` foram
concluídos; permanecem, por ordem de valor no contexto single-plant atual: particionamento/retention
(P1), refatoração de relatórios (P2) e exportação assíncrona em lote (P2).
