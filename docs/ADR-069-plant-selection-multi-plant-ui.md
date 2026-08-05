# ADR-069 — Seleção de usina na interface (multi-usina por organização)

## Status

Aceito — 2026-08-05. Todos os pontos de confirmação foram resolvidos, incluindo os quatro de § E.10:
(1) fan-out para múltiplas usinas nos jobs de coleta/alerta/orquestração fica fora de escopo,
adiado pra Etapa F; (2) FK simples com revalidação no resolvedor, não FK composta; (3) mudança de
comportamento visível do bot do Telegram (mensagens nomeando a usina, comandos `/usinas`/`/usina`
funcionais) aprovada; (4) o bug de colisão de nome de usina entre organizações diferentes em
`PlantRepository.get_or_create` é corrigido junto da Etapa E1, não em tarefa separada.

## Contexto

O usuário decidiu que a interface deve permitir operar mais de uma usina por conta. A auditoria de UI/UX (`docs/UI_UX_AUDIT_2026-08-04.md`, linha 466; `docs/UI_UX_TARGET_DESIGN_2026-08-04.md`, seção 5 item 5) apenas registrou a pergunta como pendente — "single-tenant (ADR-045) ou multi-usina na UI (ADR-052)?" — sem desenhar solução. Este ADR desenha.

### Achado que define o tamanho da frente: o modelo de dados já suporta N usinas

Verificado no código, não suposto:

- **`Plant.organization_id` já existe** (`src/mplacas/db/models.py`, linhas 72-77): `ForeignKey("organizations.id", ondelete="CASCADE")`, `nullable=False`, `index=True`. **Não há `UniqueConstraint` sobre `organization_id`** — `Plant.__table_args__` contém apenas seis `CheckConstraint` de faixa/positividade. O schema permite N usinas por organização, sem limite, hoje.
- **A autorização já é multi-usina**: `plant_scope_for_organization_in_session` (`src/mplacas/core/tenancy.py`, linhas 25-41) faz `select(Plant.id).where(Plant.organization_id == organization_id)` e devolve `PlantScope.restricted(plant_ids)` com **todas** as usinas da organização. Um usuário já está autorizado a ler qualquer usina da própria organização; simplesmente não existe superfície que lhe diga quais são.
- **`plants` já está sob RLS** por `organization_id` (migration `20260802_0040`, `ORGANIZATION_TABLES`).

Portanto **esta é uma frente de superfície, não de modelo de dados. Não há migration.** O esforço é de endpoint de listagem + estado no frontend. *(Correção 2026-08-05: vale para as Etapas A–D; a Etapa E, adicionada depois, introduz uma coluna nova em `organizations` — ver § Etapa E.)*

### ADR-045 não é obstáculo

`docs/ADR-045-mplacas-remains-single-tenant.md` fala exclusivamente do número de **organizações** atendidas ("o sistema serve uma única operação", "introduzir uma entidade de tenant"). Não menciona, em nenhum ponto, limite de **usinas por organização**. São conceitos ortogonais: uma organização pode ter vários telhados / várias UCs. Além disso, o ADR-045 já foi de fato superado pelos ADR-052/053, que introduziram `organizations` e o isolamento entre elas. Este ADR **não revoga nem revisa o ADR-045**: multi-usina dentro de uma organização é compatível com qualquer que seja o número de organizações.

### Estado atual da superfície

- **Backend**: `src/mplacas/plants/router.py` contém apenas rotas `/{plant_id}/...` (`technical-configuration` GET/PATCH, `financial-configuration` GET/PATCH, `location` PATCH). **Não existe `GET /plants`.** Não existe nenhuma forma de um cliente autenticado descobrir os `plant_id` a que tem direito.
- **Frontend**: `frontend/src/env.ts` exporta `PLANT_ID` a partir de `VITE_PLANT_ID`, validado como UUID no startup. É variável de **build**: o artefato compilado serve uma única usina. `DashboardPage.tsx` usa `PLANT_ID` em cinco pontos. O app tem apenas duas rotas (`/login`, `/dashboard`) e nenhum uso de query string.

### Achado de risco: a inferência de usina única quebra quando existe a segunda

`_infer_single_plant_for_organization_in_session` (`src/mplacas/core/tenancy.py`, linhas 121-146) lança **409** — `"plant_id is required when more than one plant exists"` — sempre que a organização tem mais de uma usina e o chamador omitiu `plant_id`. Isso é acionado por `AdminPlant` (query param opcional) e alcança hoje:

- `src/mplacas/alerts/router.py:31`
- `src/mplacas/billing/router.py:58,99,115,163`
- `src/mplacas/climate/router.py:30`
- `src/mplacas/orchestration/router.py:34,171`
- `src/mplacas/telegram/router.py:99` — **o caso grave**: o bot do Telegram resolve a usina por inferência e **não tem por onde receber um `plant_id`**.

Consequência: **cadastrar a segunda usina em uma organização hoje degrada silenciosamente o Telegram e todo chamador administrativo que omite `plant_id`** — independentemente deste ADR. O comportamento é seguro (falha fechada, 409, não vaza nem mistura dados), mas é uma quebra funcional em produção. Isso não é causado pela feature de seleção; é um débito preexistente que a feature torna alcançável.

## Decisão

### 1. Endpoint de listagem: `GET /plants`, escopo derivado do principal

Rota `GET /plants` em `src/mplacas/plants/router.py` — **não** `GET /organizations/{organization_id}/plants`. A organização nunca é aceita do cliente, é sempre derivada do principal (mesma convenção de `organizations/router.py`).

Registrar `@router.get("")` **antes** das rotas `/{plant_id}/...` no arquivo, por higiene de ordem de registro.

### 2. Autenticação: papel READ, não ADMIN

Acrescentar alias, ao lado dos existentes em `core/tenancy.py`:

```python
ReadPrincipal = Annotated[OperationsPrincipal, Depends(_read_principal)]
```

### 3. A listagem filtra por organização **e** intersecta com o `PlantScope`

- `where(Plant.organization_id == principal.organization_id)` quando definido; sem esse filtro quando é `None` (chave operacional estática da plataforma), espelhando `list_organizations`.
- Depois, filtrar por `principal.plant_scope.allows(plant.id)` — necessário porque uma credencial persistida (ADR-043) pode ter escopo explicitamente restrito a um subconjunto.

`set_principal_context(session, principal)` antes de qualquer query.

### 4. Contrato de resposta: mínimo suficiente para o seletor

```json
{
  "count": 2,
  "items": [
    { "id": "…uuid…", "name": "Matriz — Telhado A", "installed_power_kwp": "48.600" },
    { "id": "…uuid…", "name": "Filial Norte",        "installed_power_kwp": null }
  ]
}
```

- Envelope `{count, items}` — mesmo formato de `list_organizations`/`list_invitations`.
- `id`/`name`: `Plant.name` já existe. Não criar campo `nickname`.
- `installed_power_kwp`: subtítulo desambiguador. Sem `status` — `Plant` não tem essa coluna; derivar exigiria consultar telemetria por usina numa rota de listagem, custo desproporcional.
- Ordenação por `Plant.name`, desempate por `Plant.id`. Sem paginação.

### 5. Persistência da seleção: query string é a fonte da verdade, `localStorage` semeia o default

`/dashboard?plant=<uuid>` manda; `localStorage` (`mplacas_selected_plant_v1`) guarda só a última escolha, usada quando a URL chega sem o parâmetro. Limpo no `logout`, junto de `TokenStore.clear()`.

Precedência: `?plant=` válido no escopo → `localStorage` válido no escopo → primeiro item de `GET /plants`. Seleção fora do escopo é descartada silenciosamente, caindo no primeiro item — nunca vira tela de erro.

### 6. `VITE_PLANT_ID` é removido inteiramente

Não vira fallback — mantê-la reintroduziria o acoplamento que esta frente corrige. Remoções: `frontend/src/env.ts`, `.github/workflows/ci.yml`, `.github/workflows/deploy-frontend.yml`, `frontend/.env.example`, `frontend/.env.local`, `docs/runbook-producao.md`.

### 7. Quando o seletor aparece

Só quando `count > 1`. Com exatamente uma usina, o header mostra o **nome da usina como texto**, sem dropdown — ganho puro sobre hoje (que não mostra nome nenhum). Com `count == 0`, estado vazio explícito, zero chamadas de dados disparadas.

### 8. Impacto por chamada de API

Todas as chamadas que hoje leem `PLANT_ID` de `env.ts` passam a ler o `plantId` do contexto (`DashboardPage.tsx`: `FALLBACK_PV_SUMMARY`, `/energy/executive/latest`, `fetchPhotovoltaicSummary`, `fetchFinancialReturn`, `/energy/anomalies/latest`, prop do `FinancialReturnSection`). Nenhum contrato de backend muda. `useEffect`/`useCallback` de busca ganham `plantId` nas dependências.

Arquivos afetados: `src/mplacas/plants/router.py`, `src/mplacas/core/tenancy.py`, `frontend/src/env.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/dashboard/plant-contracts.ts` (novo), `frontend/src/contexts/PlantContext.tsx` (novo), `frontend/src/components/PlantSelector.tsx` (novo), `frontend/src/components/DashboardHeader.tsx`, `frontend/src/pages/DashboardPage.tsx`, `frontend/src/App.tsx`, `frontend/src/contexts/AuthContext.tsx`, testes que mockam `PLANT_ID`, e a esteira de CI/deploy.

`PlantProvider` fica **dentro** de `ProtectedRoute`, não em volta do `AuthProvider` — `GET /plants` exige autenticação.

### 9. Reviewer obrigatório

`GET /plants` é enumeração entre tenants — primeiro endpoint do projeto cuja resposta é uma lista de identificadores derivada do escopo do chamador. Pelo `CLAUDE.md` (organizations, auth), **a etapa do endpoint exige reviewer**. Frontend e limpeza de esteira, não.

## Consequências

### Positivas

- Custo baixo e proporcional: sem migration, sem mudança de autorização, sem mudança de contrato dos cinco endpoints de dados existentes.
- Resolve de brinde o P2-14 da auditoria (identidade de usina no header).
- `GET /plants` é pré-requisito de qualquer tela futura de administração de usinas.
- O artefato de frontend deixa de ser específico por usina.

### Negativas

- **A quebra por inferência (409) fica exposta** a partir do momento em que exista uma segunda usina — Telegram e chamadores administrativos que omitem `plant_id` param de funcionar. Este ADR não corrige isso; documenta e propõe guarda condicional (Etapa E).
- Uma requisição a mais bloqueante no carregamento do dashboard (aceito — tabela pequena, indexada).
- `localStorage` passa a guardar estado de sessão, assimetria com o token em memória — mitigado por limpeza no logout e validação de escopo no servidor a cada requisição.
- O caminho com dropdown não é exercitado em produção hoje (só 1 usina existe) — por isso o teste de duas usinas é obrigatório, não opcional.

## Validação

- Fronteira entre tenants: organização A com 2 usinas, organização B com 1 — principal de A recebe exatamente as suas, id de B nunca aparece.
- Escopo restrito: credencial READ com `PlantScope.restricted({p1})` em organização `{p1, p2}` lista só `p1`.
- Escopo vazio: organização sem usinas devolve 200 com `{"count": 0, "items": []}`.
- Principal de plataforma: lista todas, sem filtro por organização.
- Papel READ recebe 200.
- Frontend: `count==1` (texto, sem dropdown), `count>1` (dropdown troca query string e refaz as 5 chamadas), `count==0` (vazio, zero chamadas), `?plant=` fora do escopo (cai no primeiro, sem erro), logout limpa `localStorage`.
- `npm run build` sem `VITE_PLANT_ID` definido precisa passar.

## Reversibilidade

Alta. `GET /plants` é aditivo e removível. Seletor é frontend. Único custo de reversão é recriar `VITE_PLANT_ID` nas GitHub Variables — minutos, não migração de dados.

## Pontos confirmados pelo usuário em 2026-08-05

1. **O 409 da inferência é BLOQUEANTE, não aceito por ora.** A Etapa E (resolução de usina do Telegram/endpoints administrativos) vira pré-requisito — o seletor não é liberado pro usuário final sem isso resolvido junto. Ver § Etapa E, ao final deste documento.
2. Remoção total de `VITE_PLANT_ID` — aprovada.
3. Seletor só com `count > 1` — aprovada.
4. Query string como fonte da verdade — aprovada.
5. `name` como rótulo do seletor — aprovada.

## Plano de implementação

Cinco etapas de superfície (A–D) mais a Etapa E, detalhada logo abaixo do plano. Exigem reviewer: a Etapa A e as sub-etapas E1, E2 e E4.

**Etapa A — `GET /plants`.** Alias `ReadPrincipal`; rota com filtro duplo (organização + `plant_scope`); contrato do item 4. Sem migration, sem audit event. **Reviewer obrigatório.**

**Etapa B — camada de dados no frontend.** `fetchPlants()` + `plant-contracts.ts`. Sem reviewer.

**Etapa C — `PlantContext` e seleção**, sem UI de seletor ainda: `DashboardPage` consome `plantId` do contexto nos 6 pontos; `PLANT_ID` sai de `env.ts`. Sem reviewer.

**Etapa D — seletor no header** + limpeza de `VITE_PLANT_ID` da esteira. Sem reviewer.

**Etapa E — resolução de usina para Telegram e chamadores administrativos.** Desenhada abaixo. **Reviewer obrigatório** (toca `organizations`, migration e o caminho de ingestão de faturas).

---

## Etapa E — resolução de usina sem 409 (desenho completo)

Confirmado pelo usuário em 2026-08-05 como **bloqueante**: o seletor não é liberado sem esta etapa. Esta seção é a decisão; o resto do ADR permanece válido com uma correção — a afirmação "não há migration" (seção *Achado que define o tamanho da frente*) vale para as Etapas A–D, **não** para a Etapa E, que introduz uma coluna nova em `organizations`.

### E.1 Achado que muda o desenho: o bot do Telegram não responde perguntas

Leitura de `src/mplacas/telegram/router.py`, `service.py` e `client.py`:

- É **webhook único**, não polling, e **não** usa `MPLACAS_TELEGRAM_ALERT_CHAT_ID` para roteamento de entrada. A organização é resolvida do `chat_id` recebido, via `OrganizationRecord.telegram_chat_id` — coluna **`unique=True`** (`organizations/db_models.py:29-31`). Chat desconhecido resulta em 403, sem fallback global.
- `parse_authorized_update` (`service.py:65-68`) exige `chat_type == "private"` **e** `chat_id == user_id`, e o remetente precisa bater com `organizations.telegram_allowed_user_id`. Ou seja: **um chat, um usuário humano, uma organização** — relação 1:1:1 imposta por schema e por validação.
- O bot hoje tem **três** ramos: `command` (linha 182), que só ecoa `{"accepted": true, "kind": "command"}` **sem executar nada**; `text`; e `document`. Os dois últimos fazem uma coisa só: **parsear uma fatura da Equatorial e gravá-la como `pending_review`**.

Consequência para o enunciado da tarefa: a pergunta **não** é "sobre qual usina o dono está perguntando" (o bot não responde nada). É **"a qual usina esta fatura pertence"** — uma decisão de *atribuição de dado escrito*, não de leitura. Isso reordena os riscos: um default errado aqui não devolve um número errado numa tela, ele **grava a fatura da usina B sob a usina A**, contaminando `utility_bills`, o snapshot mensal materializado em `confirm_bill` e o retorno financeiro. Silenciar o 409 sem confirmação visível seria trocar uma falha fechada por corrupção silenciosa.

### E.2 Avaliação das opções

| Opção | Veredito |
|---|---|
| **1. Usina padrão por organização** | **Aceita, como `Organization.default_plant_id`** (FK), não como `Plant.is_default` (booleano). O booleano admite duas usinas marcadas na mesma organização e exigiria índice único parcial `WHERE is_default` particionado por `organization_id`, mais um caminho transacional de "desmarcar a anterior". A FK em `organizations` torna a unicidade verdadeira por construção, com uma escrita só. Objeção legítima do enunciado ("alguém precisa marcar") resolvida em E.4: backfill na migration mais eleição automática na criação da primeira usina, de modo que o campo nunca fica nulo pelo caminho suportado. |
| **2. Comando com parâmetro no Telegram** | **Aceita — e converge com a 1, sem custo adicional.** Como `telegram_chat_id` é `unique` em `organizations` e o chat é privado 1:1, "usina ativa deste chat" **é literalmente** "usina padrão desta organização". Não há estado de sessão a inventar nem tabela nova: `/usina <nome>` grava `organizations.default_plant_id`. O que o enunciado tratava como duas opções concorrentes é uma só decisão com duas superfícies de escrita (HTTP e chat). Rejeitada apenas a variante `/status <usina>` como *parâmetro por mensagem*: não existe `/status`, e uma fatura chega como PDF ou texto colado, sem prefixo de comando onde caberia o argumento. |
| **3. Um `chat_id` por usina** | **Rejeitada — estruturalmente impossível hoje.** `telegram_chat_id` é `unique` em `organizations` e a validação exige `chat_id == user_id` em chat privado. "Um chat por usina" implicaria um **usuário do Telegram por usina** (o dono teria de manter N contas) ou N bots com N tokens, contra `settings.telegram_bot_token` único. Custo: reescrever o vínculo chat/organização, o modelo de autorização e o provisionamento — desproporcional ao problema. |
| **4. Derivar da UC impressa na fatura** *(considerada, não pedida)* | **Rejeitada por ora, registrada como evolução.** Seria a atribuição semanticamente correta, mas `UtilityBill` (`billing/models.py:18-33`) **não tem** campo de unidade consumidora e `parse_equatorial_bill_text` não o extrai; exigiria regex nova sobre fatura real, coluna `Plant.utility_installation_number`, backfill manual por usina e um caminho de erro para UC desconhecida. E não substituiria o default: ainda precisaria de fallback quando a UC não casa. Revisitar quando existir a segunda usina real com fatura em mãos. |
| **5. Derivar do próprio recurso** *(aplicável a 2 dos 9 chamadores)* | **Aceita onde é grátis.** `confirm_bill` e `reject_bill` (`billing/router.py:111,159`) recebem `bill_id` no path e usam a usina resolvida apenas como filtro em `repository.get(bill_id, plant_id=...)`. A usina já está na linha. Trocar por "buscar por `bill_id`, validar `record.plant_id` contra `principal.plant_scope`" elimina a inferência nesses dois **sem** default e sem perda de isolamento (404 continua sendo a resposta para fatura fora do escopo). |

### E.3 Decisão

1. **Nova coluna `organizations.default_plant_id`** — `uuid`, `NULL`, `FOREIGN KEY REFERENCES plants(id) ON DELETE SET NULL`, sem índice adicional (cardinalidade 1 por linha, acesso sempre pela PK da organização).
2. **`_infer_single_plant_for_organization_in_session` passa a consultar o default antes de contar usinas.** Ordem de resolução: (a) `plant_id` explícito do chamador; (b) `default_plant_id` da organização, **revalidado** por `JOIN plants p ON p.id = o.default_plant_id AND p.organization_id = o.id` — a revalidação no read é o que garante a invariante mesmo sem FK composta (ver E.10); (c) usina única, se houver exatamente uma; (d) 409.
3. **Toda escrita de fatura passa a nomear a usina de destino na confirmação.** `_pending_message` ganha o nome da usina; `intake_bill_text` já devolve `plant_id` em `_serialize`. Sem isso, o default vira atribuição silenciosa — este item é **parte da decisão, não cosmético**.
4. **Dois comandos novos no bot**, no ramo `kind == "command"` que hoje só ecoa: `/usinas` e `/usina <nome>`.
5. **`confirm_bill` e `reject_bill` deixam de inferir usina**, passando a derivá-la do `bill_id`.
6. **Nenhuma mudança de semântica para `alerts/run`, `climate/collect`, `orchestration/run`, `orchestration/status/latest`, `billing/pending`, `billing/intake-text`**: continuam aceitando `plant_id` opcional; o que muda é apenas *para onde* a omissão resolve. Todos passam a **ecoar `plant_id` na resposta** (`orchestration/status/latest` e `alerts/run` ainda não ecoam), para que um script perceba sobre qual usina agiu.

### E.4 Como o default deixa de depender de "alguém marcar"

Três garantias, nesta ordem:

- **Backfill na própria migration**: `UPDATE organizations o SET default_plant_id = (SELECT p.id FROM plants p WHERE p.organization_id = o.id) WHERE (SELECT count(*) FROM plants p WHERE p.organization_id = o.id) = 1`. Hoje **toda** organização em produção tem exatamente uma usina, então o campo sai da migration preenchido para 100% das linhas existentes.
- **Eleição na criação**: ao criar uma usina numa organização cujo `default_plant_id` é `NULL`, a mesma transação o define. (Nota: `PlantRepository.get_or_create` — `src/mplacas/db/repositories/plant.py:20-27` — busca por `name` **sem filtrar `organization_id`** e não recebe organização; corrigir isso é pré-requisito da Etapa E1 e está listado como risco em E.10.)
- **Fallback de usina única** preservado no resolvedor (passo (c) de E.3.2), que cobre qualquer organização criada fora do caminho acima.

Resultado: o par (`default_plant_id IS NULL`, `count(plants) > 1`) é **inalcançável pelo caminho suportado**. O 409 permanece no código como asserção defensiva, com mensagem acionável, e o teste `test_default_plant_never_null_after_second_plant` prova a inalcançabilidade.

### E.5 Contratos

**PATCH `/organizations/{organization_id}`** — endpoint já existente (`organizations/router.py:346`), com `_get_own_or_404`, auditoria e o split plataforma/tenant já corretos. Ganha um campo; **não** nasce endpoint novo.

```jsonc
// request (parcial, model_fields_set)
{ "default_plant_id": "…uuid…" }   // ou null para limpar

// 200 — _organization_view ganha o campo
{ "id": "…", "name": "…", "slug": "…", "active": true,
  "telegram_chat_id": 123, "telegram_allowed_user_id": 123,
  "default_plant_id": "…uuid…" }
```

- `422` se o UUID for malformado.
- `404` se a usina não existir **ou** não pertencer a esta organização — 404, não 403/409, pela mesma razão de `resolve_read_plant`: não revelar existência de usina de outro tenant.
- Auditoria: já registrada por `fields_updated` em `AuditEventRepository`; `default_plant_id` entra na lista automaticamente. **Nada de novo a implementar em audit.**

**`GET /plants`** (Etapa A) passa a incluir `"is_default": true|false` em cada item, derivado da organização. O seletor do frontend usa isso apenas para rotular/ordenar; a precedência da seção 5 (query string, depois `localStorage`, depois primeiro item) **não muda**.

**Comandos do Telegram** — o ramo `kind == "command"` deixa de ser um eco. O webhook continua respondendo `202`; a resposta ao humano vai por `client.send_message`. Comando desconhecido responde texto de ajuda, **não** erro HTTP.

```
/usinas
-> "Usinas da sua conta:
    - Matriz — Telhado A (padrão)
    - Filial Norte
    Para trocar: /usina Filial Norte"

/usina Filial Norte
-> "Usina ativa agora: Filial Norte. As próximas faturas serão lançadas nela."

/usina Filial        -> casamento por prefixo, case-insensitive; se ambíguo, lista os candidatos e não troca
/usina Inexistente   -> "Não encontrei essa usina. Use /usinas para ver a lista."
/usina               -> mesmo efeito de /usinas
```

Resolução do nome: `ILIKE` ancorado no início, **sempre** com `Plant.organization_id == organization_id` no `WHERE` (além do RLS). Casamento exato tem precedência sobre prefixo. Zero ou 2+ candidatos: não escreve nada.

**Mensagem de fatura recebida** — `_pending_message(reference_month)` vira `_pending_message(reference_month, plant_name)`:

```
"Fatura 2026-07 recebida e analisada, lançada na usina Matriz — Telhado A.
 Ela ficou pendente de revisão humana antes da consolidação.
 Usina errada? Use /usina <nome> e reenvie."
```

### E.6 Efeito por chamador (esta tabela é o critério de aceite operacional)

| Chamador | Hoje, org com 2 usinas | Depois da Etapa E |
|---|---|---|
| `telegram/router.py:99` (texto e PDF) | **409, bot quebrado** | grava na `default_plant_id`, confirma nomeando a usina; `/usina` troca |
| `billing/router.py:58` `intake-text` | 409 se `plant_id` ausente no body | resolve pelo default; resposta já ecoa `plant_id` |
| `billing/router.py:99` `GET /pending` | 409 | resolve pelo default; ecoa `plant_id` |
| `billing/router.py:115` `confirm` | 409 | **não infere mais** — usina vem do `bill_id`, validada contra o `plant_scope` |
| `billing/router.py:163` `reject` | 409 | idem |
| `alerts/router.py:31` `POST /run` | 409 | resolve pelo default; passa a ecoar `plant_id` |
| `climate/router.py:30` `POST /collect` | 409 | resolve pelo default; ecoa `plant_id` |
| `orchestration/router.py:34` `POST /run` | 409 | resolve pelo default; ecoa `plant_id` |
| `orchestration/router.py:171` `GET /status/latest` | 409 | resolve pelo default; passa a ecoar `plant_id` |

**Limitação conhecida e aceita nesta etapa**: para os três endpoints de *execução* (`alerts/run`, `climate/collect`, `orchestration/run`), resolver pelo default significa **rodar só a usina padrão** numa organização com N usinas — as demais ficam sem coleta/alerta se o agendador não for ajustado. A alternativa correta é fan-out sobre `principal.plant_scope`, mas isso muda o contrato de resposta dos três (de objeto para lista) e o comportamento do agendador. **Fica fora da Etapa E, registrado como Etapa F.** O eco de `plant_id` na resposta é a mitigação: quem agenda vê exatamente o que rodou. **Este ponto precisa de ciência explícita do usuário** (ver E.10).

### E.7 RLS, organizations e reviewer

- Toca `organizations` (coluna nova, escrita nova) e `plants` (leitura por organização) — **ambas sob RLS** (`db/rls_inventory.py:22`, migration `20260802_0040`).
- **Ponto a verificar antes de codar** (E1): o webhook do Telegram lê `OrganizationRecord` sob `set_platform_context` e só depois faz `set_tenant_context` (`telegram/router.py:136-139`). A escrita de `/usina` e a leitura do default precisam acontecer **sob `set_tenant_context(session, organization_id)`**, e é preciso confirmar que a política de `organizations` permite `UPDATE` da própria linha nesse contexto — caso contrário o comando falha em produção e passa em SQLite. Teste em PostgreSQL real é obrigatório, não opcional.
- `_infer_single_plant_for_organization` (sessão fresca) usa `set_organization_context`; a nova query cruza `organizations` com `plants`, **duas** tabelas sob RLS na mesma transação. Verificar que ambas as políticas aceitam o mesmo GUC de contexto.
- **Reviewer obrigatório nas etapas E1, E2 e E4** (`organizations`, migration, ingestão de faturas). E3 (comandos do bot) e E5 (eco de `plant_id`) não exigem reviewer.

### E.8 Plano de implementação — seis etapas verificáveis

**E1 — migration, coluna e backfill.** `migrations/versions/20260805_0043_add_organization_default_plant.py`: coluna, FK `ON DELETE SET NULL`, backfill do parágrafo E.4, `downgrade` que dropa a coluna. Campo no `OrganizationRecord`. Corrigir `PlantRepository.get_or_create` para receber e filtrar por `organization_id` e eleger o default quando a organização não tem nenhum. *Verificável*: `alembic upgrade head` e `downgrade -1` em PostgreSQL; teste que cria organização com 1 usina e vê `default_plant_id` preenchido; teste que cria a segunda usina e vê o default **inalterado**. **Reviewer.**

**E2 — resolvedor.** Reescrever `_infer_single_plant_for_organization_in_session` com a ordem (a)–(d) de E.3.2, incluindo a revalidação por `JOIN`. A mensagem do 409 residual passa a citar `PATCH /organizations/{id}` com `default_plant_id`. *Verificável*: teste unitário das quatro ramificações, incluindo default apontando para usina de **outra** organização (deve ignorar o default e cair em (c)/(d), nunca vazar). **Reviewer.**

**E3 — comandos do bot e confirmação nomeada.** `/usinas`, `/usina <nome>`, `_pending_message` com nome da usina. *Verificável*: webhook com payload de comando troca o default e responde por `send_message` (client mockado); payload de fatura em org com 2 usinas responde `202` e grava na padrão; nome ambíguo não troca nada.

**E4 — `confirm`/`reject` derivam a usina do `bill_id`.** Remove `AdminPlant` dos dois handlers, troca por `AdminPrincipal` mais busca por `bill_id` mais `principal.require_plant_access(record.plant_id)`. *Verificável*: fatura de outra organização continua devolvendo **404**; confirmar sem `plant_id` numa org com 2 usinas funciona. **Reviewer.**

**E5 — eco de `plant_id`.** `alerts/run`, `climate/collect`, `orchestration/run`, `orchestration/status/latest` e `billing/pending` incluem `plant_id` na resposta. *Verificável*: teste de contrato por endpoint.

**E6 — `is_default` em `GET /plants` e rótulo no seletor.** Depende da Etapa A. *Verificável*: a listagem da organização traz `is_default: true` exatamente uma vez.

E1 e E2 são sequenciais. E3, E4 e E5 são paralelizáveis depois de E2. E6 depende de A e de E1.

### E.9 Critério de aceite

**Teste de aceite único, obrigatório, em PostgreSQL:** criar uma organização, criar **duas** usinas nela e, sem passar `plant_id` em lugar nenhum, exercitar **todos os nove chamadores** da tabela E.6 — os oito HTTP mais o webhook do Telegram nos dois modos (texto e PDF). **Nenhum pode responder 409.** Cada resposta precisa nomear a usina sobre a qual agiu.

Complementos:

- Fatura enviada pelo Telegram numa org com 2 usinas cai na `default_plant_id`, e a mensagem de confirmação traz o nome dela.
- `/usina <outra>` seguido de nova fatura: a fatura vai para a outra usina.
- `PATCH /organizations/{id}` com `default_plant_id` de **outra** organização: 404, e o default não muda.
- `default_plant_id` apontando para usina removida: a FK zera o campo e o resolvedor cai no fallback de usina única, sem 500.
- Credencial com `PlantScope.restricted({p2})` numa org cujo default é `p1`: resolve para o default `p1` e então **404** em `require_plant_access` — falha fechada, sem vazamento. (Comportamento aceito: escopo restrito é o único caso em que a omissão de `plant_id` ainda erra, e erra com 404, não 409.)
- Organização com **zero** usinas: continua 409, agora com mensagem acionável. Correto — não há o que resolver.

### E.10 Pontos que exigem confirmação do usuário antes de E1

1. **Fan-out não entra nesta etapa** (E.6, limitação conhecida): numa org com 2 usinas, `alerts/run`, `climate/collect` e `orchestration/run` sem `plant_id` rodarão **só a padrão**. Confirmar que isso é aceitável até a Etapa F, ou promover o fan-out para dentro da Etapa E.
2. **FK simples vs. FK composta.** O desenho usa FK simples mais revalidação no read (E.3.2). A alternativa estrita — `UNIQUE(organization_id, id)` em `plants` e FK composta `(id, default_plant_id) -> plants(organization_id, id)` — torna impossível *gravar* um default de outra organização, ao custo de um índice único redundante e de uma FK circular entre as duas tabelas. Recomendo a simples; confirmar.
3. **Mudança de comportamento do bot em produção**: as mensagens de confirmação passam a nomear a usina, e o bot passa a responder a comandos que hoje ignora. É visível para o usuário final.
4. **`PlantRepository.get_or_create` está errado hoje** (busca por `name` sem `organization_id`): duas organizações com uma usina de mesmo nome colidem. Corrigir dentro de E1 é o proposto; confirmar que pode entrar junto em vez de virar tarefa separada.

