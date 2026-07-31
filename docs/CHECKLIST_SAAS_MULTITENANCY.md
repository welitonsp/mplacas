# Checklist de remediação — Evolução SaaS Multitenancy (ADR-052 → ADR-053 → ADR-054)

Última atualização: 2026-07-31 (sessão 3 — P1 fechado: onboarding de organizações e convite de
usuário, PR-1 a PR-7)
Base: `origin/main` em `e738ec6`
Origem: seção "Próximos passos" do `ADR-052-saas-multitenancy-evolution.md`, verificada item a
item contra o código atual (não contra o texto do ADR, que estava parcialmente desatualizado).
Decisões consolidadas em `ADR-053-organization-isolation-enforced-in-routers.md` (P0) e
`ADR-054-organization-onboarding-and-user-invitations.md` (P1).

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

Gaps conhecidos deixados deliberadamente em aberto ao fim dos planos de P0 e P1. **Nenhum é
vazamento ativo de dado entre organizações via router**; todos estão registrados nas "Negativas" do
ADR-053 ou do ADR-054 para não se perderem.

- [ ] **P1 — `telegram_allowed_user_id` é um único valor global do processo.** O PR-6 do P0 garante o
  *roteamento* correto por `telegram_chat_id`, mas não há *autenticação por organização* no
  Telegram: um usuário autorizado no processo segue autorizado para qualquer chat vinculado. Gap de
  produto herdado (não introduzido pelo PR-6). Fechar exige um modelo de credencial de Telegram por
  organização (ex.: `telegram_allowed_user_id` por linha de `organizations`, ou tabela de
  associação usuário-Telegram ↔ organização). P1 porque vira problema real assim que existir uma
  segunda organização usando o canal Telegram. (ADR-053, Negativas.)
- [ ] **P2 — chaves estáticas sem prazo de desligamento.** `MPLACAS_OPERATIONS_API_KEY` /
  `MPLACAS_OPERATIONS_READ_API_KEY` continuam autenticando com `organization_id` ausente e escopo
  irrestrito — bypass legítimo de todo o isolamento. O PR-8 do P0 só instrumentou o uso. Próximo
  passo: analisar os logs/métricas de `operations_static_key_auth_used` após um período de
  observação, identificar os consumidores reais, migrá-los para credenciais persistidas com
  organização, e só então definir a data de remoção das envs. P2 porque depende de dado que ainda
  está sendo coletado; enquanto isso, o isolamento por organização é uma garantia **condicionada** à
  ausência dessas envs no ambiente. O PR-6 do P1 (org-admin por JWT em `/operations/credentials` e
  `/operations/users`) removeu o principal consumidor legítimo dessas chaves, o que torna esse
  desligamento mais viável do que era. (ADR-053, Negativas.)
- [ ] **P2 — janela de ~15 min de acesso residual após desativar uma organização.** Um access token
  JWT já emitido continua válido até expirar mesmo após `POST /organizations/{id}/deactivate`, porque
  a autenticação bearer não relê o banco a cada request. As sessões (refresh) são revogadas em lote,
  e refresh e credencial persistida já checam organização ativa — o resíduo é só o access token em
  voo. Não é regressão: mesma característica já presente na desativação de usuário
  (`credentials/router.py`, pré-existente). Fechar exige **decisão arquitetural**, não correção
  mecânica: reduzir o TTL do access token (custo de usabilidade e de carga no refresh) ou introduzir
  checagem de revogação no caminho quente (custo de latência e de um store de revogação). P2 porque
  o impacto é limitado a uma janela curta e o gatilho (desativar organização) é raro e deliberado.
  (ADR-054, Negativas; achado do PR-3 do P1.)
- [ ] **P2 — TOCTOU em `UserService.create`.** Numa corrida de `username` duplicado, o
  `IntegrityError` do banco não é capturado e vaza como 500 em vez de um 4xx claro. Pré-existente,
  mas o PR-5 do P1 passou a expô-lo por um caminho **anônimo** (`/auth/invitations/accept`), o que
  muda o perfil de quem consegue provocá-lo. Não há vazamento de dado nem usuário duplicado — a
  constraint única do banco continua valendo e a transação é descartada. Correção: capturar
  `IntegrityError` em `UserService.create` e traduzir para o mesmo 400 uniforme do aceite de convite
  (sem revelar que o `username` já existe). Tarefa de worker, escopo pequeno. P2 e não P3 por ser
  alcançável sem autenticação. (ADR-054, Negativas.)
- [ ] **P3 — comentário desatualizado em `InvitationConsumeError`.** A docstring afirma que a razão
  específica da falha é logada internamente pelo chamador; esse logging não existe. O comportamento
  de segurança está correto — só o comentário engana quem lê, sugerindo uma observabilidade que não
  há. Resolver de um dos dois jeitos: apagar a frase, ou implementar o log interno que ela promete
  (o que teria valor próprio para diagnosticar convites recusados). Item trivial de limpeza.
  (ADR-054, Negativas.)
- [ ] **P3 — ordem de rotas significativa em `organizations/router.py`.** `/invitations*` precisa
  continuar declarado antes de `/{organization_id}`; inverter não quebra import nem tipo, apenas faz
  o FastAPI casar `invitations` como se fosse um UUID. Coberto por teste e documentado no ADR-054,
  mas o código não impõe a regra sozinho. Fechar exigiria um conversor/validador explícito de UUID no
  path param. (ADR-054, Negativas.)

## P1 — Onboarding e gestão de organizações — CONCLUÍDO (2026-07-31)

Diagnóstico confirmado no início da sessão: `src/mplacas/organizations/` tinha apenas
`db_models.py`, sem `router.py`, e não havia endpoint de convite/ativação em `auth/router.py` —
criar organização ou usuário exigia acesso direto ao banco, migração manual ou
`scripts/set-admin-password.py`. A fase de desenho encontrou ainda um **bloqueador anterior aos
endpoints**: `/operations/credentials` e `/operations/users` exigiam `require_unrestricted_access()`,
e como todo bearer JWT tem escopo restrito por definição, um ADMIN de organização recebia 403 ao
administrar a própria organização. Plano de 7 PRs desenhado pelo `architect`, todos concluídos,
revisados pelo `reviewer` e publicados em `origin/main`. Decisão consolidada em
`ADR-054-organization-onboarding-and-user-invitations.md`:

- [x] **PR-1 (`7ec14ab`)**: `require_platform_admin`/`require_organization_admin` (+ aliases
  `PlatformPrincipal`/`OrgAdminPrincipal`) em `core/tenancy.py`, discriminando **por presença de
  `organization_id`**, não por granularidade do `PlantScope` — o que preserva o caso da credencial
  ADMIN persistida, restrita só por herança da organização. Sem mudança em router; fundação para os
  PRs 3, 4 e 6.
- [x] **PR-2 (`c96882b`)**: tabela `user_invitations` (migration `0026`) e `InvitationService`
  (`create`/`list`/`revoke`/`consume`/`mark_accepted`). Token só como hash SHA-256;
  `InvitationConsumeError` única e indiferenciada (não permite enumerar estado de convite);
  `mark_accepted` por UPDATE condicional contra aceite duplo; `revoke`/`list` sempre escopados por
  organização. Reviewer bloqueou divergência entre modelo e migration no índice único de
  `token_hash` — corrigida antes do commit.
- [x] **PR-3 (`75f8c35`)**: `organizations/router.py` — `POST /organizations` (`PlatformPrincipal`)
  cria organização **e convite de bootstrap ADMIN na mesma transação**, com rollback real provado
  relendo o banco; `GET /organizations` e `GET /{id}` (404, não 403, para organização alheia);
  `POST /{id}/deactivate` revoga sessões em lote. `/organizations` na allowlist do teste-guarda com
  justificativa (escopo por organização, não por usina).
- [x] **PR-4 (`26abaa4`)**: `POST/GET /organizations/invitations` e `POST .../{id}/revoke`, sob
  `OrgAdminPrincipal`. `organization_id` nunca aceito no body; token em claro só na resposta de
  criação; status derivado na hora. Achado: `/invitations*` precisa ser registrado antes de
  `/{organization_id}` (FastAPI compila o path param sem conversor de UUID).
- [x] **PR-5 (`c770d38`)**: `POST /auth/invitations/inspect` e `/accept` — os únicos endpoints que
  criam usuário e emitem sessão sem autenticação prévia, e o PR de maior risco do plano. Rate limit
  por `sha256(token)[:16]`, 400 uniforme para os cinco casos de falha, ordem
  `consume → create → mark_accepted` sem commit intermediário (sem usuário órfão em corrida).
  Revisado com o escrutínio mais alto: rate limit martelado manualmente, transação lida linha a
  linha.
- [x] **PR-6 (`e738ec6`)**: `/operations/credentials` e `/operations/users` migrados de
  `require_unrestricted_access()` para `AdminPrincipal` — corrige o bloqueador real. Deliberadamente
  `AdminPrincipal` e não `OrgAdminPrincipal`, para não excluir a chave estática de plataforma.
  Reviewer verificou isolamento cross-org de forma independente, com duas organizações reais via
  `TestClient`.
- [x] **PR-7**: `docs/ADR-054-organization-onboarding-and-user-invitations.md` + atualização deste
  checklist.

**Decisão de produto registrada:** sem integração de e-mail. O convite é entregue fora da API — o
token retorna na resposta de criação e quem convida o repassa por canal próprio. Consequências
aceitas (canal de entrega fora do controle do sistema, sem reenvio, `username` não verificado como
endereço real) estão nas "Negativas" do ADR-054.

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
| P1 (onboarding/organizações) | 7 | 0 | 0 |
| Backlog de tenancy | 0 | 0 | 6 |
| Dívida de documentação | 0 | 0 | 2 |

**P0 e P1 fechados.** O P0 (9 PRs, ADR-053) garantiu que todo router de dado valida a organização do
chamador, com a regra sustentada por um teste estrutural (`tests/test_plant_scope_guard.py`) que
quebra o CI se uma rota nova sob prefixo de dado esquecer o `ScopedPlant`. O P1 (7 PRs, ADR-054)
tornou o onboarding uma operação de API: criar organização, convidar o ADMIN inicial e aceitar o
convite deixaram de exigir acesso direto ao banco, e o ADMIN de organização passou a administrar a
própria organização por JWT — o 403 estrutural que bloqueava o self-service foi eliminado.

O que resta em tenancy é o backlog acima: um item P1 (autenticação por organização no Telegram),
três P2 (desligamento das chaves estáticas, janela de acesso residual pós-desativação, TOCTOU em
`UserService.create`) e dois P3 (comentário desatualizado, ordem de rotas). Nenhum é vazamento ativo
de dado entre organizações.
