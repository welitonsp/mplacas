# Checklist de remediação — Evolução SaaS Multitenancy (ADR-052 → ADR-053)

Última atualização: 2026-07-31 (sessão 2 — P0 fechado: PR-1 a PR-9 concluídos)
Base: `origin/main` em `37586cb`
Origem: seção "Próximos passos" do `ADR-052-saas-multitenancy-evolution.md`, verificada item a
item contra o código atual (não contra o texto do ADR, que estava parcialmente desatualizado).
Decisão consolidada em `ADR-053-organization-isolation-enforced-in-routers.md`.

Rastreia cada item pendente da evolução SaaS ao seu estado real, com a evidência correspondente.
Legenda: `[x]` concluído, `[~]` parcial, `[ ]` pendente.

## P0 — Isolamento de dados por organização — CONCLUÍDO (2026-07-31)

O diagnóstico original desta seção (grep literal por `organization_id` nos routers) foi um
**falso positivo de gravidade**. O isolamento já existia e já funcionava para `reports`,
`intelligence` e `explanations` via `PlantScope` derivado do claim `org_id` do JWT
(`core/security.py`), aplicado indiretamente — não pela string `organization_id`. O furo real era
menor em número de módulos, mas mais grave onde existia. Plano de 9 PRs desenhado pelo `architect`,
todos concluídos, revisados pelo `reviewer` e publicados em `origin/main`:

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
- [x] **PR-6 (`37586cb`)**: `telegram` associado a organização via `organizations.telegram_chat_id`
  (nullable, unique — migração `0025`). Chat sem organização vinculada recebe 403; organização com
  0 ou mais de 1 usina recebe 409. Cross-tenant provado em
  `tests/test_telegram_webhook_cross_tenant.py`.
- [x] **PR-7 — decisão sem código**: `/operations/jobs` e `/operations/status` permanecem
  **platform-only**, exigindo `require_unrestricted_access`. É o comportamento já decidido no
  ADR-037 (item 8) e já garantido de fato pela invariante do PR-1 — não houve mudança de código,
  apenas a decisão registrada (ver ADR-053, seção PR-7). Filtrar jobs por organização exigiria
  propagar `organization_id` por toda a trilha de execução, sem demanda de produto que justifique.
- [x] **PR-8 (`dc14ff0`)**: uso das chaves estáticas
  `OPERATIONS_API_KEY`/`OPERATIONS_READ_API_KEY` agora é logado (warning estruturado
  `operations_static_key_auth_used` + métrica via `record_operation`), **sem mudança de
  comportamento de autenticação**. Decisão do usuário: medir uso real antes de definir prazo de
  desligamento.
- [x] **PR-9**: `docs/ADR-053-organization-isolation-enforced-in-routers.md` + atualização deste
  checklist.
- [x] **`web`**: serve HTML estático, zero acesso a banco — nunca deveria ter estado nesta lista.

## Backlog de tenancy (não é P0 — a invariante de isolamento por organização está fechada)

Dois gaps conhecidos ficaram deliberadamente em aberto ao fim do plano. Nenhum dos dois é
vazamento ativo de dado entre organizações via router; ambos estão registrados nas "Negativas" do
ADR-053 para não se perderem.

- [ ] **P1 — `telegram_allowed_user_id` é um único valor global do processo.** O PR-6 garante o
  *roteamento* correto por `telegram_chat_id`, mas não há *autenticação por organização* no
  Telegram: um usuário autorizado no processo segue autorizado para qualquer chat vinculado. Gap de
  produto herdado (não introduzido pelo PR-6). Fechar exige um modelo de credencial de Telegram por
  organização (ex.: `telegram_allowed_user_id` por linha de `organizations`, ou tabela de
  associação usuário-Telegram ↔ organização). P1 porque vira problema real assim que existir uma
  segunda organização usando o canal Telegram.
- [ ] **P2 — chaves estáticas sem prazo de desligamento.** `MPLACAS_OPERATIONS_API_KEY` /
  `MPLACAS_OPERATIONS_READ_API_KEY` continuam autenticando com `organization_id` ausente e escopo
  irrestrito — bypass legítimo de todo o isolamento. O PR-8 só instrumentou o uso. Próximo passo:
  analisar os logs/métricas de `operations_static_key_auth_used` após um período de observação,
  identificar os consumidores reais, migrá-los para credenciais persistidas com organização, e só
  então definir a data de remoção das envs. P2 porque depende de dado que ainda está sendo
  coletado; enquanto isso, o isolamento por organização é uma garantia **condicionada** à ausência
  dessas envs no ambiente.

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
| P0 (isolamento de dados) | 10 | 0 | 0 |
| Backlog de tenancy | 0 | 0 | 2 |
| P1 (onboarding/organizações) | 0 | 0 | 2 |
| Dívida de documentação | 0 | 0 | 2 |

**P0 fechado.** Os 9 PRs do plano foram concluídos, revisados e publicados: todo router de dado do
sistema valida a organização do chamador, e a regra é sustentada por um teste estrutural
(`tests/test_plant_scope_guard.py`) que quebra o CI se uma rota nova sob prefixo de dado esquecer o
`ScopedPlant`. Não há mais vazamento de dado ativo entre organizações via router — o risco original
desta seção. O que resta em tenancy são os dois gaps de backlog acima (autenticação por organização
no Telegram e desligamento das chaves estáticas), ambos rastreados no ADR-053.
