# Inventário de rollout PostgreSQL RLS

Data do inventário: 2026-08-02. Fonte executável: `mplacas.db.rls_inventory`.

## Classes de ownership

| Classe | Tabelas | Regra planejada |
|---|---|---|
| Organização direta | `organizations`, `plants`, `api_credentials`, `auth_sessions`, `operational_users`, `user_invitations` | `id` ou `organization_id` igual ao tenant transacional |
| Planta | `collection_tasks`, `daily_climate_observations`, `daily_pv_loss_assessments`, `daily_pv_performance_results`, `daily_solar_model_results`, `devices`, `monthly_report_snapshots`, `outbox_events`, `pipeline_executions`, `report_export_tasks`, `seasonal_pv_baseline_results`, `utility_bills` | ownership resolvido por `plants.organization_id` |
| Dispositivo | `daily_energy` | `daily_energy.device_id -> devices.plant_id -> plants.organization_id` |
| Energia diária | `daily_energy_versions` | `daily_energy_versions -> daily_energy -> devices -> plants` |
| Plataforma | `alert_delivery_records`, `audit_events`, `job_runs`, `login_rate_limits` | somente bypass explícito e role PostgreSQL autorizada |

## Decisões de segurança

- O inventário é comparado em teste com todo `Base.metadata`; adicionar tabela sem classificação
  quebra a CI.
- RLS permanece desativado em produção nesta etapa.
- `audit_events` ainda não possui `organization_id`. Antes de policies produtivas, decidir e migrar
  tenant explícito para novos eventos, preservando registros históricos de plataforma.
- Autenticação, refresh, credenciais persistidas e descoberta de planta inicializam contexto de
  plataforma/tenant antes da primeira consulta. Os helpers registram o contexto também em
  `session.info`, permitindo auditoria em SQLite sem fingir suporte a RLS.
- Jobs, drains, retenção, webhook Telegram e operações globais estão contextualizados
  explicitamente. Um teste AST inspeciona todos os consumidores diretos de `SessionFactory()` e
  falha se a primeira operação não for um dos helpers de contexto.
- Contexto de plataforma ainda não significa acesso irrestrito: quando as policies forem ativadas,
  o banco também exigirá membership na role PostgreSQL mínima prevista pela ADR-056.

## Gate para a próxima etapa

O gate de contextualização das sessões foi atendido. Não criar a migration de ativação até modelar
tenant em `audit_events`, definir as policies para cada classe de ownership e preparar a role
PostgreSQL mínima de plataforma. O canário final deve usar branch Neon descartável, executar testes
CRUD cross-tenant e ensaiar downgrade/rollback antes de produção.
