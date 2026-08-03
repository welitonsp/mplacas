# Runbook de rollout PostgreSQL RLS

Data: 2026-08-02. Estado: policies aprovadas em canário; **não ativadas em produção**.

## Controles implementados

- 24 tabelas classificadas e cobertas por `ENABLE/FORCE ROW LEVEL SECURITY`.
- Tenant ausente recebe zero linhas e não grava.
- Bypass exige `mplacas.platform_bypass=on` e membership em `mplacas_platform`.
- `audit_events.organization_id` é nullable para preservar histórico e eventos globais.
- `alert_delivery_records.plant_id` é nullable para preservar histórico; novos registros são
  isolados e deduplicados por planta.
- O contexto é restaurado automaticamente em cada transação após `commit()`.
- A migration 0040 recusa upgrade sem
  `MPLACAS_RLS_ACTIVATION_APPROVED=ENABLE-RLS-20260802`.
- `scripts/validate-rls-canary.py` cria e remove um database descartável com nome protegido.

## Repetir o canário

Use exclusivamente o endpoint direto de migrations. Não exiba ou grave a URL:

```powershell
$migrationSecret = gcloud secrets versions access latest `
  --secret=mplacas-migration-database-url --project=mplacas
$env:MPLACAS_MIGRATION_DATABASE_URL = $migrationSecret
try {
  .venv\Scripts\python.exe scripts/validate-rls-canary.py
} finally {
  Remove-Item Env:MPLACAS_MIGRATION_DATABASE_URL
}
```

Aceite somente se a saída contiver:

```text
rls_enabled=24 policies=24 helper_functions=2
2 passed
rls_enabled=0 policies=0 helper_functions=0
rls_enabled=24 policies=24 helper_functions=2
1 passed
rls_canary=passed
canary_database_dropped=...
```

`--full-history-cycle` também testa downgrade até `base`; é diagnóstico de migrations antigas e
não substitui o rollback obrigatório 0040 -> 0039.

## Pré-condições para produção

1. Confirmar backup/restauração recente e janela de mudança.
2. Confirmar revisão backend com contexto transacional em 100% do tráfego.
3. Confirmar `mplacas_runtime` como `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE` e `NOBYPASSRLS`.
4. Criar a marker role sem login e membership sem capacidade de assumi-la:

```sql
CREATE ROLE mplacas_platform NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT mplacas_platform TO mplacas_runtime
  WITH INHERIT FALSE, SET FALSE, ADMIN FALSE;
```

No PostgreSQL 18, confirme em `pg_auth_members` que `inherit_option`, `set_option` e
`admin_option` estão falsos. A role não recebe privilégios em tabelas; ela funciona apenas como
segundo fator para a função de policy.

## Ativação controlada

O job normal não recebe a variável de aprovação e deve falhar fechado na 0040. Durante a janela:

1. Atualize temporariamente `mplacas-migrate` com
   `MPLACAS_RLS_ACTIVATION_APPROVED=ENABLE-RLS-20260802`.
2. Execute o job uma vez e confirme Alembic head `20260802_0040`.
3. Remova imediatamente a variável de aprovação do job.
4. Confirme no catálogo: 24 tabelas com `relrowsecurity` e `relforcerowsecurity`, 24 policies e duas
   funções auxiliares.
5. Execute `/health`, `/ready`, smoke, watchdog, login/refresh, Telegram, relatório e drain de
   outbox.
6. Monitore erros de policy, HTTP 5xx e latência por pelo menos uma janela operacional definida.

Não habilite a variável no serviço web e não a salve em Secret Manager.

## Rollback

Se qualquer fluxo falhar:

1. Use o endpoint direto de migrations e execute `alembic downgrade 20260802_0039`.
2. Confirme 0 tabela RLS, 0 policy e 0 função auxiliar.
3. Reexecute smoke/watchdog e os fluxos afetados.
4. Revogue `mplacas_platform` de `mplacas_runtime`; remova a marker role somente após confirmar que
   nenhuma outra identidade depende dela.
5. Preserve logs, IDs de revisão/job e horário do incidente no checklist.
