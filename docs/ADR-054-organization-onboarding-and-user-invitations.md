# ADR-054 — Onboarding de organizações e convite de usuário (fechamento do P1 do ADR-052)

## Status

Aceito.

## Contexto

O ADR-052 introduziu a entidade `Organization`, o claim `org_id` no JWT e o papel operacional por
usuário; o ADR-053 fechou o P0 correspondente, garantindo que todo router de dado valida a
organização do chamador. Restava o item P1 da seção "Próximos passos" do ADR-052, rastreado em
`docs/CHECKLIST_SAAS_MULTITENANCY.md`: **não havia como criar uma organização nem um usuário pela
API**. `src/mplacas/organizations/` continha apenas `db_models.py`, sem `router.py`, e nenhum
endpoint de convite/ativação existia em `auth/router.py`. Na prática, onboarding exigia acesso
direto ao banco, migração manual ou `scripts/set-admin-password.py` — o que inviabiliza qualquer
operação self-service e concentra em quem tem credencial de banco uma tarefa que é de produto.

O diagnóstico da fase de desenho encontrou, além da ausência de endpoints, um **bloqueador de
autorização anterior a eles**: `/operations/credentials` e `/operations/users` exigiam
`require_unrestricted_access()`. Como todo bearer JWT tem escopo restrito por definição (deriva da
organização — invariante estabelecida no PR-1 do ADR-053), um ADMIN de organização autenticado por
JWT recebia **403 ao administrar a própria organização**. Só a chave estática de plataforma passava.
Ou seja: mesmo depois de criar a organização e o usuário admin, esse admin não conseguiria criar
mais nada. O plano precisou corrigir isso, e não apenas adicionar rotas novas.

A distinção que faltava no código era entre três níveis de principal administrativo, até então
achatados em um só:

1. **plataforma** — quem pode criar organizações (hoje, na prática, apenas a chave estática, único
   principal ADMIN sem `organization_id`);
2. **admin de organização** — quem administra a própria organização (JWT ou credencial persistida
   com `organization_id`);
3. **admin genérico** — qualquer um dos dois, para endpoints que devem servir aos dois.

O ADR-053 já havia criado `core/tenancy.py` como o lugar canônico das dependencies de tenancy; este
ADR estende o mesmo módulo em vez de abrir um segundo mecanismo paralelo de autorização.

O trabalho foi decomposto em 7 PRs de escopo fechado, cada um com CI verde e revisão independente
pelo `reviewer`, conforme a política de `CLAUDE.md` para mudanças em auth/credentials/organizations/
migrations.

## Decisão

### PR-1 (`7ec14ab`) — Dependencies `require_platform_admin` / `require_organization_admin`

`core/tenancy.py` ganha duas dependencies e seus aliases `PlatformPrincipal` / `OrgAdminPrincipal`,
ao lado do `AdminPrincipal` já existente. A discriminação é feita **pela presença de
`organization_id`, não pela granularidade do `PlantScope`** — decisão central deste PR:

- `require_platform_admin`: rejeita com 403 qualquer principal com `organization_id` definido.
- `require_organization_admin`: rejeita com 409 o principal de plataforma (`organization_id is
  None`), porque não há organização a administrar — 409 e não 403, pela mesma lógica de
  `resolve_admin_plant` quando a organização não permite inferir a usina.

O caso de interseção mais sutil foi verificado explicitamente em teste: uma credencial ADMIN
persistida nunca tem `plant_ids` explícito (proibido em `CredentialService.create`), logo seu escopo
é restrito **por herança da organização** — e ainda assim precisa passar em
`require_organization_admin`. Discriminar por granularidade de escopo, e não por `organization_id`,
teria quebrado exatamente esse caso.

Nenhum router foi alterado neste PR: é fundação para os PRs 3, 4 e 6.

### PR-2 (`c96882b`) — Modelo e serviço de convite

Nova tabela `user_invitations` (migration `20260731_0026_add_user_invitations.py`), com
`organization_id`, `username`, `role`, `token_hash`, `created_by_user_id`, `expires_at`,
`accepted_at`, `accepted_user_id` e `revoked_at`. TTL configurável via
`MPLACAS_AUTH_INVITATION_TTL_SECONDS` (default 72h). `InvitationService` expõe
`create`/`list`/`revoke`/`consume`/`mark_accepted`.

Decisões de segurança do modelo:

- **O token nunca é persistido em claro.** Só o hash SHA-256 (`token_hash`, único e indexado). Quem
  perder o token não o recupera do banco; só resta revogar e emitir outro.
- **`InvitationConsumeError` é única e indiferenciada.** `consume()` levanta a mesma exceção para
  expirado, revogado, já aceito, organização inativa e não encontrado. Deliberado: um token roubado
  ou adivinhado não deve servir para enumerar o estado de um convite.
- **`mark_accepted` usa UPDATE condicional** (`WHERE accepted_at IS NULL`, checando `rowcount`)
  contra a corrida de aceite duplo — a exclusão mútua fica no banco, não em leitura prévia na
  aplicação.
- **`revoke`/`list` são sempre escopados por `organization_id`**, nunca por ID isolado.
- `username` de convite exige formato de e-mail (decisão do usuário); usernames legados não-e-mail
  continuam funcionando, sem validação retroativa.

A revisão bloqueou uma divergência entre modelo e migration no índice único de `token_hash` (a
migration criava `UniqueConstraint` + índice comum separados; o modelo gera um único índice
`unique=True`); corrigida e reverificada antes do commit.

### PR-3 (`75f8c35`) — `organizations/router.py`

- `POST /organizations` (`PlatformPrincipal`): cria a organização **e o convite de bootstrap do
  ADMIN na mesma transação**. Se o convite falhar (por exemplo, `admin_username` inválido), ambos
  sofrem rollback — verificado relendo o banco no teste, não apenas pelo código de resposta. Isso
  elimina o estado intermediário "organização criada, sem nenhum administrador", do qual só se sairia
  por intervenção manual.
- Slug duplicado responde 409 por pre-check (aceitável dado o volume baixo de criação de
  organização).
- `GET /organizations` lista todas para a plataforma e apenas a própria para uma organização;
  `GET /{id}` de organização alheia responde **404, não 403**, mantendo a convenção do ADR-037/053 de
  não confirmar a existência de recurso alheio.
- `POST /{id}/deactivate` revoga em lote as `auth_sessions` ativas da organização, via o novo
  `AuthSessionService.revoke_all_for_organization`.

O router foi registrado em `main.py`, e `/organizations` foi adicionado a `_DATA_PREFIXES` do
teste-guarda do ADR-053 com entrada de allowlist justificada: o escopo destas rotas é por
organização (`PlatformPrincipal`/`AdminPrincipal`) e não por usina, então elas não declaram
`ScopedPlant` por desenho.

### PR-4 (`26abaa4`) — Endpoints de gestão de convite

`POST /organizations/invitations`, `GET /organizations/invitations` e
`POST /organizations/invitations/{id}/revoke`, todos sob `OrgAdminPrincipal`.

- `organization_id` **nunca** é aceito no corpo: sempre derivado do principal, mesmo princípio já
  usado em `credentials/router.py`.
- O token em claro aparece **apenas na resposta de criação**. O `GET` nunca inclui `token` nem
  `token_hash` — testado por inspeção das chaves do JSON, não por comparação de valor.
- O status é derivado na hora (`PENDING`/`ACCEPTED`/`REVOKED`/`EXPIRED`), com precedência
  `ACCEPTED > REVOKED > EXPIRED > PENDING`; não há coluna de estado a manter sincronizada.
- Revogar convite de outra organização responde 404, não 403.

Achado de implementação registrado para quem mexer no router depois: as rotas `/invitations*`
precisaram ser declaradas **antes** de `/{organization_id}`, porque o FastAPI compila o path param
sem conversor implícito de UUID e a ordem inversa causa colisão. Confirmado pelo reviewer com
request real via `TestClient`, não apenas lendo o código.

### PR-5 (`c770d38`) — Aceite anônimo de convite

`POST /auth/invitations/inspect` e `POST /auth/invitations/accept`: os **únicos endpoints do sistema
que criam usuário e emitem sessão sem autenticação prévia do chamador**. Foi o PR de maior risco do
plano e recebeu o escrutínio mais alto na revisão.

- Rate limit reusa `LoginRateLimitService`, com chave derivada de `sha256(token)[:16]` — isola a
  tentativa de brute-force por token.
- Todos os casos de falha (inválido, expirado, aceito, revogado, organização inativa) são traduzidos
  para o **mesmo 400 uniforme**, sem diferenciar o motivo — a decisão do PR-2 propagada até a
  fronteira HTTP.
- **Ordem crítica na transação**, confirmada linha a linha pela revisão: `UserService.create` só roda
  após `consume` ter sucesso; `mark_accepted` só roda após `create` ter sucesso; se `mark_accepted`
  perder a corrida (outro aceite concorrente já consumiu o convite), levanta o mesmo 400 **sem commit
  intermediário**, e a sessão descarta o usuário recém-inserido no fechamento — sem órfão.
- `UserService.create` ganha `password_hash` opcional (argon2id via `hash_password`). Todos os call
  sites existentes foram conferidos por grep: nenhum passou a poder omitir senha sem querer.
- O `TokenResponse` devolvido é idêntico ao de `/auth/login`. Senha mínima de 12 caracteres, sem
  regra de composição.

### PR-6 (`e738ec6`) — `/operations/credentials` e `/operations/users` sob `AdminPrincipal`

Correção do bloqueador real descrito no Contexto. Os seis handlers (create/list/revoke de credencial,
create/list/deactivate de usuário) trocam `require_operations_key` + `require_unrestricted_access()`
por `AdminPrincipal`.

Decisão deliberada: **`AdminPrincipal`, não `OrgAdminPrincipal`.** Usar `OrgAdminPrincipal` excluiria
a chave estática de plataforma, que precisa continuar funcionando enquanto existir (ver ADR-053,
PR-8). `AdminPrincipal` aceita as duas fontes; o papel ADMIN já é imposto a montante em
`require_operations_key`. `_resolve_organization_id` continua derivando exclusivamente de
`principal.organization_id`, nunca de input da requisição, e todos os métodos de
`CredentialService`/`UserService` usados por esses handlers já filtram por `organization_id` na
query — não há bypass.

A revisão verificou o isolamento cross-org de forma independente, com duas organizações reais via
`TestClient`: listagem alheia retorna zero resultados, operação por ID alheio retorna 404, a chave
estática continua funcionando e o papel READ continua bloqueado.

### PR-7 — Este ADR e a atualização do checklist.

## Consequências

### Positivas

- **Onboarding deixa de exigir acesso ao banco.** Criar organização, convidar o ADMIN inicial e
  aceitar o convite são operações de API, auditáveis e testáveis. `scripts/set-admin-password.py` e a
  migração manual deixam de ser o caminho de criação de usuário.
- **Não existe estado intermediário "organização sem admin".** A criação da organização e do convite
  de bootstrap compartilham a transação (PR-3), com rollback real provado em teste.
- **A distinção plataforma / organização virou explícita no código** (`PlatformPrincipal` vs.
  `OrgAdminPrincipal` vs. `AdminPrincipal`), no mesmo `core/tenancy.py` do ADR-053, em vez de um
  segundo mecanismo de autorização paralelo. Cada endpoint novo escolhe entre três dependencies
  nomeadas, e a escolha fica legível na assinatura do handler.
- **Um 403 estrutural foi eliminado** (PR-6): o admin de organização passa a administrar a própria
  organização por JWT, sem depender da chave estática de plataforma. Isso também reduz a pressão para
  manter as chaves estáticas vivas — o principal consumidor legítimo delas era exatamente esse
  caminho bloqueado. Não fecha o item de backlog do ADR-053, mas remove um obstáculo real a fechá-lo.
- **O token de convite não é recuperável do banco.** Um dump de `user_invitations` não permite
  aceitar convite nenhum.
- A superfície anônima nova é estreita e explícita: dois endpoints, ambos com rate limit por token e
  resposta de erro uniforme.

### Negativas

- **Janela de ~15 minutos de acesso residual após desativar uma organização.** Um access token JWT já
  emitido continua válido até expirar mesmo depois de `POST /organizations/{id}/deactivate`, porque a
  autenticação bearer não relê o banco a cada request. O PR-3 revoga as sessões (refresh) em lote, e
  tanto o refresh quanto a autenticação por credencial persistida já checam organização ativa — o
  resíduo é apenas o access token em voo. **Não é regressão deste esforço**: é a mesma característica
  já presente na desativação de usuário (`credentials/router.py`, pré-existente). Aceita
  conscientemente na revisão do PR-3. As duas saídas possíveis — reduzir o TTL do access token, ou
  introduzir uma checagem de revogação no caminho quente — têm custo próprio (usabilidade ou
  latência) e ficam como decisão arquitetural de backlog, não como correção pendente.
- **TOCTOU em `UserService.create`.** Numa corrida de `username` duplicado, o `IntegrityError` do
  banco não é capturado e vaza como 500 em vez de um 4xx claro. É **pré-existente**, mas o PR-5 passou
  a expô-lo por um caminho **anônimo** (`/auth/invitations/accept`), o que muda o perfil de quem
  consegue provocá-lo. Não é vazamento de dado nem cria usuário duplicado — a constraint única do
  banco continua sendo respeitada e a transação é descartada. Registrado como backlog técnico, não
  bloqueante.
- **Comentário desatualizado em `InvitationConsumeError`.** A docstring afirma que a razão específica
  da falha é logada internamente pelo chamador, e esse logging não existe. O comportamento de
  segurança está correto (a mensagem pública realmente não diferencia os casos), mas o comentário
  induz quem lê a acreditar que há observabilidade do motivo real da falha — e não há. Item trivial
  de limpeza: ou apagar a frase, ou implementar o log que ela promete.
- **Sem integração de e-mail — decisão explícita do usuário.** O convite não é entregue pela API: o
  token retorna na resposta de criação e quem convida o repassa por canal próprio. Consequências
  aceitas: (a) o token trafega por um canal fora do controle do sistema, e sua confidencialidade
  depende de quem convida; (b) não há reenvio nem recuperação de convite perdido — perdeu o token,
  revoga e cria outro; (c) o `username` do convite não é verificado como endereço real de ninguém,
  apenas validado em formato. Integrar um provedor de e-mail é evolução direta: não exige mudar o
  modelo de dados nem o contrato HTTP, apenas somar uma entrega ao `InvitationService`.
- **A ordem de declaração das rotas em `organizations/router.py` é significativa.** `/invitations*`
  precisa vir antes de `/{organization_id}`. É uma armadilha silenciosa: inverter a ordem não quebra
  import nem tipo, só faz o FastAPI casar `invitations` como se fosse um UUID de organização. Está
  documentado no PR-4 e coberto por teste, mas continua sendo conhecimento que o código não impõe
  sozinho.
- **`create_organization` faz pre-check de slug em vez de tratar a violação de unicidade.** Aceito
  pelo volume baixíssimo de criação de organização, mas é o mesmo padrão TOCTOU do item acima, em
  escala muito menor.

## Validação

- `tests/test_tenancy.py`: cobre `require_platform_admin`/`require_organization_admin`, incluindo o
  caso de interseção (credencial ADMIN persistida, com escopo restrito por herança da organização,
  passa em `require_organization_admin`).
- `tests/test_user_invitations.py`: ciclo completo do `InvitationService` — criação, listagem,
  revogação, consumo, expiração, aceite duplo concorrente e uniformidade de `InvitationConsumeError`.
- `tests/test_organizations_router.py`: criação de organização com convite de bootstrap, rollback
  real verificado relendo o banco, 409 de slug duplicado, 404 (não 403) para organização alheia,
  revogação de sessões na desativação, e ausência de `token`/`token_hash` no `GET` de convites.
- `tests/test_invitation_acceptance.py`: aceite anônimo ponta a ponta, os cinco casos de falha
  convergindo para o mesmo 400, rate limit por token, e a corrida de aceite duplo com duas sessões
  reais sem deixar usuário órfão.
- `tests/test_credentials.py` e `tests/test_operational_users.py`: isolamento cross-org do PR-6
  verificado com duas organizações reais via `TestClient` (listagem vazia, 404 por ID alheio), chave
  estática de plataforma preservada, papel READ ainda bloqueado.
- `tests/test_plant_scope_guard.py`: o teste-guarda estrutural do ADR-053 continua verde, com as
  rotas de `/organizations` na allowlist e justificativa escrita.
- Migration `0026` com `upgrade`/`downgrade`, e `migrations/env.py` atualizado para enxergar o modelo
  novo.
- Cada um dos seis PRs com código foi revisado pelo `reviewer` antes do commit. A revisão do PR-2
  bloqueou uma divergência modelo/migration que teria produzido um índice a mais em produção; a do
  PR-5 verificou a ordem da transação linha a linha e martelou o rate limit manualmente.

## Reversibilidade

Os pontos de reversão são três, independentes entre si:

1. **Autorização** — `require_platform_admin`/`require_organization_admin` em `core/tenancy.py`.
   Voltar `/operations/credentials` e `/operations/users` a `require_unrestricted_access()` é uma
   troca de dependency por handler, e faria falhar os testes cross-org de `tests/test_credentials.py`
   e `tests/test_operational_users.py` — que é o comportamento desejado.
2. **Superfície anônima** — os dois endpoints em `auth/router.py`. Removê-los ou fechá-los atrás de
   autenticação não afeta o resto do fluxo: o convite continua sendo criado e listado normalmente,
   apenas o aceite volta a exigir intervenção administrativa.
3. **Modelo de dados** — a tabela `user_invitations` (migration `0026`, com `downgrade`). É aditiva:
   nenhuma tabela existente foi alterada, então o rollback não toca dado pré-existente.

A decisão de não integrar e-mail é o ponto de extensão mais provável: somar uma entrega ao
`InvitationService` não exige mudança de schema nem de contrato HTTP, já que o token continua sendo
gerado e hasheado do mesmo jeito.

## Referências

- ADR-052: evolução SaaS multitenancy — origem da entidade `Organization` e do claim `org_id` no JWT;
  este ADR fecha o item P1 ("onboarding e gestão de organizações") de seus "Próximos passos".
- ADR-053: isolamento por organização aplicado nos routers — precedente direto do mecanismo
  `AdminPrincipal` / `PlantScope` em `core/tenancy.py`, estendido aqui com `PlatformPrincipal` e
  `OrgAdminPrincipal`. A invariante "credencial com organização nunca é irrestrita", estabelecida
  lá, é o que torna a discriminação por `organization_id` confiável aqui.
- ADR-044: usuários operacionais nomeados — base de `UserService`, estendido no PR-5 com
  `password_hash` opcional.
- ADR-043: credenciais persistidas — `CredentialService.create`, cuja proibição de `plant_ids`
  explícito em credenciais ADMIN é o que sustenta o caso de interseção do PR-1.
- ADR-037: convenção de responder 404 (e não 403) para recurso fora do escopo do chamador, seguida
  em `GET /organizations/{id}` e na revogação de convite alheio.
- `docs/CHECKLIST_SAAS_MULTITENANCY.md`: rastreamento PR a PR, com hashes de commit.
