# ADR-053 — Isolamento por organização aplicado nos routers (fechamento do P0 do ADR-052)

## Status

Aceito.

## Contexto

O ADR-052 introduziu a entidade `Organization` e o claim `org_id` no JWT, mas registrou
explicitamente em "Negativas / Limites atuais" que o isolamento era **estrutural no schema, não
aplicado nas queries**, e listou como primeiro "Próximo passo" (P0) propagar a organização como
contexto de autorização nos routers de dados. Este ADR registra a execução desse passo e o fecha.

O diagnóstico inicial que motivou o trabalho (um grep literal por `organization_id` nos routers)
era **parcialmente errado** e superestimava a gravidade. O isolamento já existia e já funcionava
para `reports`, `intelligence` e `explanations`: o `PlantScope` do ADR-037 passou a ser derivado do
claim `org_id` do JWT em `core/security.py`, aplicado indiretamente — a string `organization_id`
simplesmente não aparecia no código do router. O furo real era mais estreito em número de módulos,
porém mais grave onde existia, e tinha quatro naturezas distintas:

1. **Invariante quebrada na origem.** `credentials/service.py:_scope_for_credential` concedia
   `PlantScope` irrestrito a credenciais persistidas com `plant_ids=None` — o caso normal de uma
   credencial `ADMIN` — mesmo quando a credencial tinha `organization_id` definido. Nenhuma
   checagem posterior no router poderia corrigir isso, porque o escopo já chegava irrestrito.
2. **Routers que resolviam `plant_id` manualmente**, cada um com sua própria função de resolução
   sem filtro de organização (`billing`, `alerts`, `orchestration`, `climate`). O pior caso era
   `billing/router.py` (dado financeiro, leitura e escrita) via `_resolve_plant_scope`.
3. **Um webhook sem noção de organização**: `telegram/router.py` resolvia a usina com um
   `SELECT Plant.id LIMIT 2` global — correto por acidente enquanto o produto era single-tenant de
   fato, e silenciosamente errado a partir da segunda organização.
4. **Um bypass de plataforma**: as chaves estáticas `MPLACAS_OPERATIONS_API_KEY` /
   `MPLACAS_OPERATIONS_READ_API_KEY` autenticam com `organization_id` ausente e escopo irrestrito,
   anulando qualquer isolamento aplicado acima enquanto existirem em produção.

Este ADR também formaliza a superação definitiva do ADR-045 ("Mplacas permanece single-tenant"),
que já havia sido revertido de fato pelo ADR-052: a extensão prevista na seção "Reversibilidade"
do ADR-045 (derivar o escopo de usina a partir do tenant, preservando papéis e a mecânica de
credenciais) é exatamente o que foi implementado, com `organization_id` no lugar de `tenant_id`.

O trabalho foi decomposto em 9 PRs de escopo fechado, cada um com CI verde e revisão independente,
rastreados em `docs/CHECKLIST_SAAS_MULTITENANCY.md`.

## Decisão

### PR-1 (`8fb1ad9`) — Invariante: credencial com organização nunca é irrestrita

`credentials/service.py:_scope_for_credential` passa a derivar o `PlantScope` a partir das usinas
da organização quando `plant_ids` é `None` e `organization_id` está definido. A derivação foi
extraída para o módulo novo `core/tenancy.py` (`plant_scope_for_organization` /
`plant_scope_for_organization_in_session`), reusado tanto pela autenticação por JWT quanto pelas
credenciais persistidas. O remendo condicional em `require_plant_access`, que cobria esse caso
apenas parcialmente, foi removido.

Invariante resultante, hoje a base de todo o resto: **uma credencial com `organization_id` definido
nunca recebe `PlantScope` irrestrito.** Como efeito colateral, restaura-se o comportamento já
decidido no ADR-037 item 8 — credenciais restritas recebem 403 em `/operations/jobs` e
`/operations/status`.

### PR-2 (`5471ab0`) — Dependency `ReadPlant`/`AdminPlant` e teste-guarda estrutural

`core/tenancy.py` ganha as dependencies `ReadPlant` e `AdminPlant`, que resolvem e validam o
`plant_id` **antes** do handler e entregam um `ScopedPlant` (`plant_id` + `principal`). Fora do
escopo, a resposta é 404 e não 403, preservando a decisão do ADR-037 de não confirmar a existência
de usina alheia. `AdminPlant` infere a usina única da organização quando `plant_id` é omitido, e
responde 409 quando a organização tem zero ou mais de uma usina — a inferência global anterior
deixa de existir.

`tests/test_plant_scope_guard.py` torna a regra estrutural e verificável: toda rota sob um prefixo
de dado precisa declarar um parâmetro anotado com `ScopedPlant` ou constar de uma allowlist com
justificativa escrita. O teste percorre `_IncludedRouter.effective_route_contexts()` para enxergar
as rotas realmente despachadas pelo FastAPI, não os wrappers de `app.routes`.

`reports`, `intelligence` e `explanations` foram migrados como prova de conceito.

Ainda neste PR, `OperationsPrincipal` e `OperationsRole` foram extraídos para o módulo neutro
`core/principal.py`. A primeira versão usava um monkey-patch (`tenancy.OperationsPrincipal = ...`)
para resolver type hints, o que dependia da ordem de import em `main.py` e quebraria em 500 no
runtime assim que os PRs seguintes removessem imports diretos de `core.security` — falha silenciosa
em produção, apontada na revisão.

### PR-3 (`7ac97ae`) — `billing/router.py`

Router financeiro migrado para `ReadPlant`/`AdminPlant`; `_resolve_plant_scope` (sem filtro de
organização) removido. Era o furo mais grave do plano, por cobrir leitura e escrita de dado
financeiro. O `plant_id` que chega no corpo da requisição (`intake_bill_text`) usa
`resolve_admin_plant_scope`, a mesma função por trás da dependency, para não abrir um segundo
caminho de validação.

### PR-4 (`fc924d1`) — `alerts/router.py` e `orchestration/router.py`

Ambos migrados. Achado adicional da implementação: `GET /pipeline/status/latest` não tinha
**nenhuma** autorização por usina antes — não era um caso de filtro incompleto, era ausência total.

### PR-5 (`4c8b421`) — `climate/router.py`

Última migração de router. A revisão fez auditoria independente das 31 rotas efetivas da aplicação
e confirmou que nenhuma rota de dado ficou sem `ScopedPlant` nem sem justificativa de allowlist
válida. A allowlist remanescente é permanente e estruturalmente justificada: as duas rotas de
exportação por `task_id`, os endpoints de gestão/plataforma de `/operations`, o `plant_id` que
`billing` recebe no corpo, e o webhook do Telegram.

### PR-6 (`37586cb`) — Telegram roteado por organização

Nova coluna `organizations.telegram_chat_id` (nullable, unique), migração
`migrations/versions/20260731_0025_add_telegram_chat_id_to_organizations.py`. O webhook resolve a
organização a partir do chat de origem **antes** de qualquer processamento: chat sem organização
vinculada recebe 403, sem fallback silencioso; organização com zero ou mais de uma usina recebe
409, pelo mesmo critério de `resolve_admin_plant`. A autenticação por `telegram_webhook_secret` /
`telegram_allowed_user_id` não muda. `tests/test_telegram_webhook_cross_tenant.py` prova o
isolamento entre duas organizações com `chat_id` distintos via `TestClient`.

### PR-7 — `/operations/*` permanece platform-only (decisão sem código)

`/operations/jobs` e `/operations/status` continuam exigindo acesso irrestrito
(`require_unrestricted_access`): são endpoints de plataforma, não de organização. A alternativa —
filtrar os registros de job por organização e abri-los a credenciais escopadas — foi descartada por
ora, pois exigiria propagar `organization_id` por toda a trilha de execução de jobs sem demanda de
produto que a justifique.

Não há mudança de código associada: o comportamento decidido no ADR-037 item 8 já é garantido de
fato pela invariante do PR-1 (credencial com organização nunca é irrestrita). O PR existe apenas
para registrar que a decisão foi tomada conscientemente, e não esquecida.

### PR-8 (`dc14ff0`) — Chaves estáticas: medir antes de depreciar

Toda autenticação bem-sucedida por `OPERATIONS_API_KEY` / `OPERATIONS_READ_API_KEY` passa a emitir
um warning estruturado (`operations_static_key_auth_used`, com papel, `credential_id` e
método/caminho HTTP — nunca a chave em claro) e uma métrica via `record_operation`. **Nenhum
comportamento de autenticação muda**: mesmas comparações `hmac.compare_digest`, mesma ordem de
checagem, mesmas exceções.

Decisão explícita do usuário: começar apenas com observabilidade, sem depreciar ainda. O prazo de
desligamento será definido a partir do uso real medido, não por estimativa.

### PR-9 — Este ADR.

## Consequências

### Positivas

- A invariante "todo router de dado valida a organização do chamador" está fechada e é
  **verificável por teste**, não por convenção: `tests/test_plant_scope_guard.py` falha o CI se uma
  rota nova sob prefixo de dado esquecer o `ScopedPlant`. Um esquecimento futuro vira erro de CI, e
  não incidente de vazamento.
- A validação de escopo saiu do corpo dos handlers para a camada de dependency. Deixou de haver N
  implementações de `_resolve_plant_scope` divergindo entre si.
- Defesa em profundidade preservada: o erro de origem (PR-1) e o erro de aplicação (PR-2 a PR-6)
  foram corrigidos separadamente; nenhum dos dois depende do outro para valer.
- Dois bugs pré-existentes foram descobertos pelo caminho: `GET /pipeline/status/latest` sem
  autorização alguma (PR-4) e o roteamento global do Telegram (PR-6). Ambos só apareceriam em
  produção com a segunda organização real.
- O ADR-052 pode deixar de listar o isolamento nos routers como limite atual.

### Negativas

- **`telegram_allowed_user_id` continua sendo um único valor global do processo.** O PR-6 garante
  que a fatura vá para a organização certa (roteamento por `telegram_chat_id`), mas **não** é
  autenticação por organização: um usuário autorizado no processo continua autorizado para
  qualquer chat vinculado. É um gap de produto conhecido, herdado e não introduzido pelo PR-6, e
  exige um modelo de credencial de Telegram por organização para ser fechado. Rastreado como
  backlog em `docs/CHECKLIST_SAAS_MULTITENANCY.md`.
- **As chaves estáticas ainda não têm prazo de desligamento.** Enquanto
  `MPLACAS_OPERATIONS_API_KEY` / `MPLACAS_OPERATIONS_READ_API_KEY` existirem no ambiente, elas
  autenticam com `organization_id` ausente e escopo irrestrito — um bypass legítimo de todo o
  isolamento descrito acima. O PR-8 apenas instrumentou o uso. Enquanto esse dado não for
  analisado, o isolamento por organização é uma garantia **condicionada** à ausência dessas envs no
  ambiente. Também rastreado como backlog.
- `AdminPlant` sem `plant_id` explícito agora responde 409 quando a organização tem mais de uma
  usina, onde antes inferia "a" usina globalmente. É mudança de comportamento observável para
  qualquer cliente que dependia da omissão do parâmetro — aceita conscientemente, porque a
  inferência global era exatamente o bug.
- `core/tenancy.py` usa imports resolvidos preguiçosamente (`_read_principal` / `_admin_principal`)
  para quebrar o ciclo com `core/security.py`. Funciona e está documentado no módulo, mas é uma
  indireção a mais que quem lê o código precisa entender.
- A allowlist do teste-guarda é mantida à mão. Ela protege contra esquecimento, não contra alguém
  adicionar uma entrada nova com justificativa fraca.

## Validação

- `tests/test_tenancy.py`: cobre a derivação de escopo por organização e a invariante do PR-1.
- `tests/test_plant_scope_guard.py`: teste estrutural sobre as rotas efetivas da aplicação; a
  allowlist encolheu a cada PR (PR-2 a PR-5) até restarem apenas as entradas permanentes.
- `tests/test_telegram_webhook_cross_tenant.py`: duas organizações com `chat_id` distintos,
  exercitadas ponta a ponta via `TestClient`, permanecem isoladas.
- `tests/test_credentials.py`, `tests/test_operational_users.py`,
  `tests/test_operations_router.py`: atualizados para o comportamento restaurado do ADR-037 (403
  para credencial restrita em `/operations/*`).
- Migração `0025` com `upgrade`/`downgrade`.
- Auditoria manual independente, na revisão do PR-5, das 31 rotas efetivas da aplicação.
- Cada um dos oito PRs com código foi revisado pelo `reviewer` antes do merge, conforme a política
  de `CLAUDE.md` para mudanças em billing/auth/credentials/organizations/migrations. A revisão do
  PR-2 evitou uma falha de runtime em produção (monkey-patch de type hints).

## Reversibilidade

O ponto de reversão é `core/tenancy.py`: as dependencies `ReadPlant`/`AdminPlant` são a única porta
de entrada da validação de escopo nos routers de dado. Afrouxar o modelo (por exemplo, voltar a
permitir escopo irrestrito para uma credencial com organização) exigiria mudar
`_scope_for_credential` e `resolve_*_plant` — e faria `tests/test_plant_scope_guard.py` e
`tests/test_tenancy.py` falharem, que é o comportamento desejado. Este ADR **substitui na prática o
ADR-045**, cuja premissa single-tenant já não valia desde o ADR-052.

## Referências

- ADR-052: evolução SaaS multitenancy — pai direto deste esforço; este ADR fecha o item P0 de seus
  "Próximos passos".
- ADR-045: decisão single-tenant original, superada pelo ADR-052 e definitivamente encerrada aqui.
- ADR-037: origem do `PlantScope` e da decisão de manter `/operations/jobs` e `/operations/status`
  negados a credenciais restritas (item 8), confirmada pelo PR-7.
- ADR-043/044: credenciais persistidas e usuários nomeados, base sobre a qual o escopo por
  organização foi derivado.
- ADR-032: trilha de auditoria por `credential_id`.
- `docs/CHECKLIST_SAAS_MULTITENANCY.md`: rastreamento PR a PR, com hashes de commit.
