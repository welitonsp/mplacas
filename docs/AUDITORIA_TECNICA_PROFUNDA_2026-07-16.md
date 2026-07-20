# Auditoria técnica profunda - Mplacas

> **Status de remediação (2026-07-20):** o acompanhamento item a item do roadmap desta auditoria
> está em `CHECKLIST_REMEDIACAO_AUDITORIA.md`. Todos os P0 e P1 de curto prazo foram concluídos;
> RBAC (single-tenant) e fila/workers também. Pendentes: particionamento/retention, refatoração de
> relatórios, cache de dashboard, exportação em lote e `plant_id` obrigatório em faturas.

Data: 2026-07-16  
Base auditada: `main` alinhada a `origin/main` em `8a7e8fc`  
Validação local: `pytest` 136 passed, `ruff check .` passed, `mypy` passed

## 1. Resumo executivo

O Mplacas está em bom estado para um produto operacional inicial: é um monólito modular FastAPI assíncrono, com regras determinísticas separadas em serviços/engines, persistência SQLAlchemy/Alembic, testes amplos, CI com lint/typecheck/testes, container não-root e scripts de implantação com guardrails de custo no Google Cloud Run.

A arquitetura atual se aproxima de um modular monolith com camadas por domínio. Não é Clean Architecture estrita nem hexagonal completa, mas já isola bem provedores externos, regras energéticas, billing, clima, alertas, orquestração e relatórios.

Os maiores riscos para os próximos 10 anos são: controle de acesso ainda baseado em uma única chave operacional, endpoints operacionais públicos, observabilidade incompleta para jobs, inconsistências transitórias de multiusina por `plant_id` nullable, falta de alguns índices compostos para crescimento e crescimento rápido de módulos de relatório muito grandes.

## 2. Mapeamento

Stack principal:

- Linguagem: Python >= 3.12, validado localmente com Python 3.13.
- API: FastAPI e Uvicorn.
- Banco: SQLAlchemy async, Alembic, PostgreSQL em produção e SQLite para dev/testes.
- Externos: NEPViewer, Open-Meteo, Telegram Bot API, gateway HTTP configurável para explicações assistidas por IA.
- Relatórios: CSV, PDF via ReportLab e XLSX via XlsxWriter.
- Deploy: Docker, Cloud Run, Cloud Run Jobs e scripts Bash em `infra/gcp/`.
- Qualidade: Pytest, Ruff, Mypy, ShellCheck no CI.

Organização:

- `src/mplacas/billing`: faturas, parser e reconciliação.
- `src/mplacas/intelligence`: indicadores, tendências, anomalias e dashboard executivo.
- `src/mplacas/climate`: coleta e persistência climática.
- `src/mplacas/alerts`: candidatos, ledger SQL e entrega Telegram.
- `src/mplacas/orchestration`: pipeline diário e ledger de execução.
- `src/mplacas/reports`: relatórios mensais e exportadores CSV/PDF/XLSX.
- `src/mplacas/operations`: status operacional e histórico de jobs.
- `src/mplacas/providers`: adaptadores externos, especialmente NEPViewer.
- `migrations/versions`: evolução do schema.

O que está bem feito:

- Regras energéticas determinísticas fora de IA generativa: `src/mplacas/intelligence/energy_engine.py`.
- Segredos modelados com `SecretStr`, produção bloqueia SQLite e exige chave operacional: `src/mplacas/core/config.py:97-113`.
- Autenticação operacional falha fechada: `src/mplacas/core/security.py:10-28`.
- Adaptadores externos isolados e com timeout: `src/mplacas/providers/nepviewer/client.py:38-40`, `src/mplacas/climate/open_meteo.py:22-29`.
- Relatórios não recalculam indicadores e desativam fórmulas/URLs no XLSX: `src/mplacas/reports/xlsx_exporter.py:541-550`.
- CI cobre testes, Ruff, Mypy, ShellCheck e smoke test de container: `.github/workflows/ci.yml:18-27`, `.github/workflows/ci.yml:34-44`, `.github/workflows/ci.yml:79-112`.
- Container roda como usuário não-root: `Dockerfile:18`.

Aceitável no estágio atual:

- Modular monolith por domínio, sem separação rígida por portas/casos de uso.
- SQLite em dev/testes, PostgreSQL obrigatório em produção.
- Dashboard estático público que pede a chave operacional no navegador, sem persistir em localStorage.

Deve ser refatorado:

- `src/mplacas/reports/xlsx_exporter.py` tem 550 linhas, `reports/service.py` 521 e `pdf_exporter.py` 347. A área de relatórios já virou um bloco de apresentação complexo.
- Serviços executivos repetem consultas e recalculam ciclo atual ao montar dashboard, tendências e relatórios.
- Autorização precisa sair de chave operacional única para identidade, escopo por usina e RBAC.

Representa risco:

- `/operations/jobs` e `/operations/status` não usam `require_operations_key`: `src/mplacas/operations/router.py:9-40`.
- Cloud Run é implantado com `--allow-unauthenticated`: `infra/gcp/deploy-service.sh:50`.
- Falhas do Cloud Run Job diário podem ser perdidas por rollback: `src/mplacas/cloud_jobs.py:145-147`.

## 3. Avaliação arquitetural

Classificação: modular monolith em camadas, com tendência a ports/adapters nos provedores externos.

Não há evidência de microservices. Também não há Clean Architecture pura: routers chamam serviços diretamente e a composição fica espalhada em endpoints, por exemplo `src/mplacas/orchestration/router.py:61-74` e `src/mplacas/reports/router.py:30-42`.

Problemas encontrados:

| Problema | Gravidade | Impacto | Solução recomendada |
|---|---|---|---|
| Chave operacional única para API administrativa e dashboard | Alta | Não escala para SaaS, auditoria por usuário ou isolamento multiusina | Introduzir identidade, tenants, RBAC e escopos por `plant_id` |
| Endpoints `/operations/*` públicos | Alta | Vazamento de metadados operacionais, status, métricas e erros | Aplicar `Depends(require_operations_key)` ou autenticação própria |
| Relatórios concentrados em módulos grandes | Média | Mudanças de layout/exportação ficam frágeis e difíceis de revisar | Separar builders de dados, renderizadores, estilos e contratos |
| Composição de use cases em routers | Média | Endpoints acumulam decisões de infraestrutura e domínio | Criar application services/cases explícitos |
| Sem interface formal para métricas/tracing | Média | Dificulta diagnóstico em produção | Padronizar telemetry facade e instrumentação OpenTelemetry |

## 4. Avaliação de domínio e DDD

Há bom uso de dataclasses imutáveis e engines determinísticos em billing, qualidade, saúde, anomalias e energia. Exemplos: `UtilityBill.validate()` em `src/mplacas/billing/models.py`, `analyze_energy_cycle()` em `src/mplacas/intelligence/energy_engine.py` e `calculate_plant_health()` em `src/mplacas/health/engine.py`.

Aderência a DDD: parcial. Existem entidades persistidas e objetos de domínio, mas agregados não estão formalizados. Os models SQLAlchemy ainda são usados diretamente nos serviços, e há conversões manuais entre persistência e domínio, como `_to_domain_bill()` em `src/mplacas/intelligence/cycle_service.py:30-44`.

Riscos de domínio:

- `plant_id` nullable em faturas legado cria regra especial de escopo: `src/mplacas/billing/db_models.py:34-36`, `src/mplacas/intelligence/cycle_service.py:59-63`.
- `source_hash` é único globalmente: `src/mplacas/billing/db_models.py:55`. Isso é bom para idempotência, mas pode bloquear casos multiusina se duas unidades tiverem documento textual idêntico ou importações migradas.
- O dashboard mensal é derivado de dashboard executivo, não de um caso de uso próprio de relatório: `src/mplacas/reports/service.py:114-121`. Isso economiza lógica, mas acopla relatório a decisões de apresentação executiva.

## 5. Avaliação de banco

Pontos fortes:

- Constraints únicas para dispositivos, energia diária, faturas, clima, alertas e execução de pipeline: `migrations/versions/20260712_0001_initial_energy_schema.py:56-80`, `20260713_0006_add_plant_coordinates_and_climate.py:44-51`, `20260713_0007_add_pipeline_executions.py:45-51`.
- Ledger de alertas por fingerprint com índice único: `migrations/versions/20260713_0004_add_alert_delivery_records.py:30-33`.
- PostgreSQL obrigatório em produção: `src/mplacas/core/config.py:99-108`.

Riscos:

- Falta índice explícito em `devices.plant_id`, usado em joins por usina em `src/mplacas/intelligence/cycle_service.py:81` e `src/mplacas/intelligence/anomaly_service.py:73`.
- Consultas de faturas usam `plant_id`, `status`, `cycle_end`, `created_at`, mas migrations têm índices simples, não composto para o padrão: `src/mplacas/intelligence/executive_service.py:93-99`, `migrations/versions/20260712_0003_utility_bills.py:46-48`, `20260713_0005_scope_utility_bills_by_plant.py:26`.
- `daily_energy_versions` não tem índice explícito em `daily_energy_id`, apesar da FK.
- Não há particionamento/retention para tabelas de séries temporais (`daily_energy`, `daily_climate_observations`, ledgers).

Melhorias imediatas:

- Criar índices `devices(plant_id)`, `utility_bills(plant_id, status, cycle_end desc, created_at desc)` e `daily_energy_versions(daily_energy_id)`.
- Definir política de retenção/arquivamento para `job_runs`, `pipeline_executions`, `alert_delivery_records`.

Melhorias futuras:

- Avaliar particionamento mensal/anual em `daily_energy` e clima quando passar de milhares de usinas.
- Tornar `utility_bills.plant_id` obrigatório após migração completa de legado.

## 6. Segurança

O sistema não apresenta sinais fortes de SQL injection: as queries usam SQLAlchemy `select()` e parâmetros tipados. XSS no dashboard é mitigado por `textContent`, e PDF escapa texto com `html.escape`: `src/mplacas/reports/pdf_exporter.py:35`.

Vulnerabilidades e riscos:

- Alta: endpoints operacionais públicos. `operations_router` não tem dependência de autenticação em `src/mplacas/operations/router.py:9`, enquanto outros routers administrativos usam `Depends(require_operations_key)`, por exemplo `src/mplacas/billing/router.py:17-20`.
- Alta futura: chave operacional única sem RBAC, claims, rotação por usuário ou auditoria de ator. Para SaaS/multiusina isso é insuficiente.
- Média: URLs externas configuráveis sem allowlist para gateway de IA e clima: `src/mplacas/core/config.py:34-37`, uso em `src/mplacas/explanations/http_provider.py:79-87` e `src/mplacas/climate/open_meteo.py:51-57`. Como são env vars, o risco exige controle de configuração, mas vale restringir em produção.
- Média: Cloud Run `--allow-unauthenticated` é aceitável apenas se todos endpoints sensíveis tiverem autenticação; hoje `/operations/*` quebra essa premissa.
- Baixa: Telegram download valida tamanho e assinatura PDF, mas processamento de PDF ainda deve ter limites de páginas/tempo revisados continuamente.

## 7. Observabilidade

Existe:

- `/health` e `/ready`: `src/mplacas/main.py:42-89`.
- `job_runs` com status, duração, métricas e erro: `src/mplacas/operations/models.py`.
- `pipeline_executions` com stage, tentativa e status: `src/mplacas/orchestration/db_models.py`.
- Logs estruturados por `logger.info(..., extra={...})` em pipeline, clima, alertas e jobs.

Falta:

- Tracing distribuído.
- Métricas Prometheus/OpenTelemetry.
- Correlation/request ID.
- Alertas reais sobre SLOs, falhas repetidas e pipelines presos.
- Registro confiável de falha no Cloud Run Job diário: `src/mplacas/cloud_jobs.py:145-147` desfaz por rollback o estado marcado em `src/mplacas/orchestration/runtime.py:79-86`.

Implementar imediatamente:

- Corrigir rollback do Cloud Run Job para persistir falhas no ledger.
- Proteger `/operations/*`.
- Adicionar request ID e logging middleware.

## 8. Performance

Backend:

- Baixo/médio impacto: consultas atuais são pequenas e bem testadas, mas o dashboard e relatório recalculam caminho executivo inteiro.
- Médio impacto: `build_executive_dashboard()` chama ciclo atual e, em seguida, tendência, que chama novamente análise de ciclos: `src/mplacas/intelligence/executive_service.py:103-114`, `src/mplacas/intelligence/history_service.py:154-157`.
- Médio/alto futuro: exportadores PDF/XLSX geram tudo em memória: `src/mplacas/reports/pdf_exporter.py:233` e `src/mplacas/reports/xlsx_exporter.py:541-548`. Para relatório mensal de uma usina está ok; para lote de muitas usinas, precisa job assíncrono/storage.

Frontend:

- Dashboard é estático e leve, sem framework e sem armazenamento persistente de chave.
- Baixo risco de re-render ou bundle size.

## 9. Escalabilidade

100 usinas: arquitetura atual deve operar bem se PostgreSQL estiver dimensionado e jobs forem seriados.

1.000 usinas: gargalos prováveis em índices de consulta por usina/data, agendamento de jobs, rate limits de NEPViewer/Open-Meteo/Telegram e ausência de fila.

10.000 usinas: monólito ainda pode servir API, mas coleta/processamento deve ir para filas e workers. Relatórios devem ser assíncronos, cacheados e armazenados.

100.000 usinas: exige arquitetura de ingestão/eventos, particionamento de séries temporais, filas, cache, storage de relatórios, multi-tenant real, SLOs e observabilidade robusta.

Gargalos futuros:

- Jobs síncronos chamados por endpoints administrativos.
- Sem fila/backpressure.
- Sem cache materializado para dashboards.
- Sem particionamento/retention.
- Autorização não modela tenant/usuário/usina.

## 10. Qualidade de código

Notas:

| Área | Nota |
|---|---:|
| Arquitetura | 7.5 |
| Organização | 8.0 |
| Escalabilidade | 6.0 |
| Segurança | 6.5 |
| Performance | 7.0 |
| Qualidade de código | 8.0 |
| Testabilidade | 8.5 |

Evidências positivas:

- 136 testes passando.
- Ruff limpo.
- Mypy limpo em 102 source files.
- Muitos domínios têm testes específicos.

Dívida técnica:

- Arquivos grandes em relatórios.
- Regras transitórias de legado multiusina.
- Autorização simples demais.
- Observabilidade sem métricas/tracing.
- Índices ainda insuficientes para escala.

## 11. Roadmap de evolução

Correções urgentes - 30 dias:

| Item | Impacto | Complexidade | Prioridade |
|---|---|---:|---:|
| Persistir falhas do Cloud Run Job diário, removendo rollback que apaga ledger | Alto | Baixa | P0 |
| Proteger `/operations/jobs` e `/operations/status` | Alto | Baixa | P0 |
| Adicionar índices `devices(plant_id)`, `utility_bills(plant_id,status,cycle_end,created_at)` e `daily_energy_versions(daily_energy_id)` | Alto | Média | P0 |
| Definir allowlist/validação de URLs externas em produção | Médio | Baixa | P1 |
| Adicionar request ID e middleware de logging | Médio | Média | P1 |

Melhorias táticas - 90 dias:

| Item | Impacto | Complexidade | Prioridade |
|---|---|---:|---:|
| Introduzir RBAC/tenant/user para acesso por usina | Alto | Alta | P1 |
| Remover `plant_id` nullable de faturas após migração de legado | Alto | Média | P1 |
| Materializar snapshot mensal para dashboard/relatórios | Médio | Média | P1 |
| Refatorar relatórios em contrato, projeção, renderizadores e estilos | Médio | Média | P2 |
| Adicionar métricas OpenTelemetry/Prometheus e alertas de SLO | Alto | Média | P1 |

Melhorias estratégicas - 6 a 12 meses:

| Item | Impacto | Complexidade | Prioridade |
|---|---|---:|---:|
| Migrar coleta/processamento para fila e workers | Alto | Alta | P1 |
| Implementar particionamento/retention para séries temporais e ledgers | Alto | Alta | P1 |
| Criar cache/read models para dashboards executivos | Médio | Média | P2 |
| Exportação assíncrona em lote com storage de artefatos | Médio | Média | P2 |
| Formalizar arquitetura de tenants, auditoria de ator e trilha de alterações | Alto | Alta | P1 |

## 12. Tabela consolidada

| Item | Gravidade | Impacto | Esforço | Prioridade |
|---|---|---|---|---|
| Falha de Cloud Run Job não persistida por rollback | Alta | Perda de observabilidade operacional | Baixo | P0 |
| `/operations/*` sem autenticação | Alta | Exposição operacional em Cloud Run público | Baixo | P0 |
| Chave operacional única sem RBAC | Alta | Bloqueia SaaS/multi-tenant seguro | Alto | P1 |
| Índices insuficientes para consultas por usina/ciclo | Alta | Lentidão em 1k+ usinas | Médio | P0 |
| `plant_id` nullable em faturas legadas | Média | Ambiguidade de domínio multiusina | Médio | P1 |
| Relatórios com módulos muito grandes | Média | Manutenção frágil | Médio | P2 |
| Ausência de tracing/métricas | Média | Diagnóstico lento em produção | Médio | P1 |
| URLs externas sem allowlist | Média | Risco de configuração perigosa | Baixo | P1 |
| Exportação PDF/XLSX em memória | Média | Gargalo em exportação em lote | Médio | P2 |
| Sem filas/backpressure para crescimento | Alta futura | Gargalo em 10k+ usinas | Alto | P1 |

