# Checklist de remediação — Evolução SaaS Multitenancy (ADR-052)

Última atualização: 2026-07-31 (sessão 2 — PR-1 a PR-5 concluídos e publicados)
Base: `origin/main` em `4c8b421`
Origem: seção "Próximos passos" do `ADR-052-saas-multitenancy-evolution.md`, verificada item a
item contra o código atual (não contra o texto do ADR, que estava parcialmente desatualizado).

Rastreia cada item pendente da evolução SaaS ao seu estado real, com a evidência correspondente.
Legenda: `[x]` concluído, `[~]` parcial, `[ ]` pendente.

## P0 — Isolamento de dados por organização (diagnóstico corrigido em 2026-07-31)

O diagnóstico original desta seção (grep literal por `organization_id` nos routers) foi um
**falso positivo de gravidade**. O isolamento já existe e já funciona para `reports`,
`intelligence` e `explanations` via `PlantScope` derivado do claim `org_id` do JWT
(`core/security.py`), aplicado indiretamente — não pela string `organization_id`. O furo real é
menor em número de módulos, mas mais grave onde existe:

- [x] **PR-1 (`8fb1ad9`)**: invariante "credencial com `organization_id` nunca tem `PlantScope`
  irrestrito" — `credentials/service.py:_scope_for_credential` corrigido; `core/tenancy.py` criado.
- [x] **PR-2 (`5471ab0`)**: dependency `ReadPlant`/`AdminPlant` + teste-guarda anti-regressão
  (`tests/test_plant_scope_guard.py`), migrando `reports`/`intelligence`/`explanations` como prova
  de conceito. Refatorado para `core/principal.py` após o reviewer identificar um monkey-patch
  frágil de resolução de type hints.
- [x] **PR-3 (`7ac97ae`)**: `billing/router.py` isolado por organização — era o furo mais grave
  (financeiro). `_resolve_plant_scope` (sem filtro de organização) removido.
- [x] **PR-4 (`fc924d1`)**: `alerts/router.py` e `orchestration/router.py` isolados. Achado
  adicional: `GET /pipeline/status/latest` não tinha NENHUMA autorização por usina — corrigido.
- [x] **PR-5 (`4c8b421`)**: `climate/router.py` isolado — última migração de router. Reviewer fez
  auditoria independente das 31 rotas efetivas da app e confirmou que nenhuma rota de dado ficou
  sem `ScopedPlant` nem sem justificativa de allowlist válida. **Invariante "todo router de dado
  valida organização" fechada para billing/alerts/orchestration/climate/reports/intelligence/
  explanations.**
- [ ] **`telegram`, `operations`**: não vazam dado (fail-closed hoje), mas quebram
  funcionalmente assim que existir uma segunda organização — exigem decisão de modelo de dados,
  não são apenas código (PR-6 e PR-7 do plano do architect, bloqueados aguardando decisão).
- [ ] **Chaves estáticas `OPERATIONS_API_KEY`/`OPERATIONS_READ_API_KEY`**: concedem
  `organization_id=None` com escopo irrestrito — bypass total de qualquer isolamento aplicado
  acima enquanto essas envs existirem em produção (PR-8, bloqueado aguardando plano de migração).
- [x] **`web`**: serve HTML estático, zero acesso a banco — nunca deveria ter estado nesta lista.

Plano de remediação em 9 PRs desenhado pelo `architect` em 2026-07-31. PR-1 a PR-5 concluídos,
revisados pelo `reviewer` e publicados em `origin/main`. PR-6/7/8 bloqueados aguardando decisão de
produto/modelo de dados; PR-9 (ADR-053 + doc) pendente até os anteriores fecharem.

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
| P0 (isolamento de dados) | 7 | 0 | 2 |
| P1 (onboarding/organizações) | 0 | 0 | 2 |
| Dívida de documentação | 0 | 0 | 2 |

**PR-1 a PR-5 concluídos, revisados e publicados** — a invariante de isolamento por organização
está fechada para todos os routers de dados do sistema. Restam em P0 apenas os dois itens que
exigem decisão de produto/modelo de dados antes de qualquer código (telegram/operations, PR-6/7) e
o plano de depreciação das chaves estáticas (PR-8) — nenhum dos três é mais um vazamento de dado
ativo entre organizações via router de dados, que era o risco original desta seção.
