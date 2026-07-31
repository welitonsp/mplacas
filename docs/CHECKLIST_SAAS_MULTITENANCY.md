# Checklist de remediação — Evolução SaaS Multitenancy (ADR-052)

Última atualização: 2026-07-31 (sessão 2 — diagnóstico P0 corrigido pelo architect)
Base: `origin/main` em `fd5ca36`
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

- [ ] **`billing`, `orchestration`, `alerts`, `climate`**: routers usam
  `dependencies=[Depends(require_operations_key)]` no nível do router, então o `OperationsPrincipal`
  nunca é injetado no handler — `plant_id` chega cru de query/body sem qualquer validação de
  organização. Um usuário autenticado da org B pode confirmar/rejeitar fatura da org A
  (`billing`), disparar pipeline (`orchestration`) ou alerta via Telegram (`alerts`) sobre dado de
  outra organização. **Este é o P0 real.**
- [ ] **`credentials/service.py:173`**: uma credencial ADMIN persistida sem `plant_ids` explícito
  recebe `PlantScope` irrestrito mesmo tendo `organization_id` definido — contido só por um
  remendo condicional em `security.py` que não cobre todos os caminhos de uso do `plant_scope`.
- [ ] **`telegram`, `operations`**: não vazam dado (fail-closed hoje), mas quebram
  funcionalmente assim que existir uma segunda organização — exigem decisão de modelo de dados,
  não são apenas código (ver PR-6 e PR-7 do plano do architect).
- [ ] **Chaves estáticas `OPERATIONS_API_KEY`/`OPERATIONS_READ_API_KEY`**: concedem
  `organization_id=None` com escopo irrestrito — bypass total de qualquer isolamento aplicado
  acima enquanto essas envs existirem em produção.
- [x] **`reports`, `intelligence`, `explanations`**: já isolados via `PlantScope`/JWT — removidos
  da lista de pendências.
- [x] **`web`**: serve HTML estático, zero acesso a banco — nunca deveria ter estado nesta lista.

Plano de remediação em 9 PRs desenhado pelo `architect` em 2026-07-31 (não documentado aqui em
detalhe — ver histórico da sessão). PR-1 (invariante de escopo) em execução.

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
| P0 (isolamento de dados) | 2 | 0 | 4 |
| P1 (onboarding/organizações) | 0 | 0 | 2 |
| Dívida de documentação | 0 | 0 | 2 |

**6 itens de código pendentes em P0/P1, 2 já concluídos em P0 (reports/intelligence/explanations e
web) reclassificados nesta revisão, 1 item já concluído em outra frente (refresh token) mas não
documentado, 2 pendências de documentação.** Os quatro itens P0 restantes (billing/orchestration/
alerts/climate sem validação de organização, invariante de escopo em credentials, telegram/
operations quebrados por design single-tenant, chaves estáticas como bypass) têm risco de
segurança ativo e devem ser tratados antes de P1.
