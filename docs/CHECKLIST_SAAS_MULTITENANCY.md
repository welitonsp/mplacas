# Checklist de remediação — Evolução SaaS Multitenancy (ADR-052)

Última atualização: 2026-07-30 (sessão 1)
Base: `origin/main` em `cb1f236`
Origem: seção "Próximos passos" do `ADR-052-saas-multitenancy-evolution.md`, verificada item a
item contra o código atual (não contra o texto do ADR, que estava parcialmente desatualizado).

Rastreia cada item pendente da evolução SaaS ao seu estado real, com a evidência correspondente.
Legenda: `[x]` concluído, `[~]` parcial, `[ ]` pendente.

## P0 — Isolamento de dados por organização

- [ ] **Extrair `organization_id` do JWT e aplicar como contexto de autorização nos routers de
  dados.** Verificado em 2026-07-30: `billing/router.py`, `climate/router.py`,
  `intelligence/router.py`, `reports/router.py`, `operations/router.py`, `alerts/router.py`,
  `explanations/router.py`, `orchestration/router.py`, `telegram/router.py` e `web/router.py` têm
  zero ocorrências de `organization_id` — nenhum filtro de isolamento aplicado. Apenas
  `auth/router.py` e `credentials/router.py` já filtram. **Prioridade máxima**: sem isso, qualquer
  usuário autenticado de uma organização pode ler/gravar dados de outra organização nesses módulos
  — é uma falha de isolamento multi-tenant, não apenas dívida técnica.

## P1 — Onboarding e gestão de organizações

- [ ] **Endpoint `GET/POST /organizations`.** Verificado: `src/mplacas/organizations/` contém
  apenas `db_models.py`; não existe `router.py`. Hoje, criar uma organização nova exige acesso
  direto ao banco ou migração — bloqueia onboarding self-service.
- [ ] **Fluxo de convite/ativação de usuário.** Verificado: nenhum endpoint de
  invite/activation em `auth/router.py`. Usuários só são criados via CLI admin ou migração
  (`scripts/set-admin-password.py`).

## Concluído (confirmar e fechar a lacuna de documentação)

- [x] **Revogação de refresh token.** Verificado: `auth/session_service.py` já implementa
  `revoke()` e a coluna `revoked_at` (migration `20260726_0024_auth_sessions_rate_limits_roles.py`).
  O `ADR-052` ainda lista esse item como pendente em "Próximos passos" — **precisa ser corrigido**
  para não induzir a próxima sessão a redescobrir/reimplementar algo que já existe.

## Dívida de documentação (não é código, mas engana quem lê)

- [ ] Atualizar `ADR-052-saas-multitenancy-evolution.md`: mover "revogação de refresh token" de
  "Próximos passos" para "Decisão" (Phase 2), já que está implementado.
- [ ] Revisar a issue #2 do GitHub ("Roadmap técnico do Mplacas — P1 a P4"): todos os checkboxes
  estão desmarcados apesar de a maioria dos itens (Postgres/migrations, backup/restore, backfill,
  parser Equatorial, reconciliação, anomalias, dashboard, exportação PDF/CSV/Excel, multi-usina)
  já estar implementada no código. Fechar ou reescrever para refletir o estado real — do contrário
  é uma fonte de verdade enganosa para quem só olhar o GitHub.

## Resumo

| Categoria | Concluídos | Parciais | Pendentes |
|---|---:|---:|---:|
| P0 (isolamento de dados) | 0 | 0 | 1 |
| P1 (onboarding/organizações) | 0 | 0 | 2 |
| Dívida de documentação | 0 | 0 | 2 |

**3 itens de código pendentes, 1 já concluído mas não documentado, 2 pendências de
documentação.** O item P0 (isolamento por `organization_id`) é o único com risco de segurança
ativo e deveria ser tratado antes dos demais.
