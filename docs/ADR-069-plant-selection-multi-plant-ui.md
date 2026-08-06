# ADR-069 — Seleção de usina na interface (multi-usina por organização)

## Status

Aceito — 2026-08-05. Todos os pontos de confirmação foram resolvidos, incluindo os quatro de § E.10:
(1) fan-out para múltiplas usinas nos jobs de coleta/alerta/orquestração fica fora de escopo,
adiado pra Etapa F — **revisado em 2026-08-06: o usuário decidiu o oposto; o fan-out foi promovido
para dentro da Etapa E, ver § E.11**; (2) FK simples com revalidação no resolvedor, não FK composta; (3) mudança de
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

> **Nota de correção — 2026-08-06.** A versão original desta etapa, aceita em 2026-08-05, registrava
> em § E.10 item 1 como "limitação conhecida e aceita" que `alerts/run`, `climate/collect` e
> `orchestration/run` sem `plant_id` rodariam **só na usina padrão**, adiando o fan-out para uma
> "Etapa F". **Por decisão explícita do usuário, essa limitação foi revogada: o fan-out entra dentro
> da Etapa E.** As seções § E.6, § E.8, § E.9 e § E.10 foram reescritas para refletir isso, e a
> § E.11 (nova) contém o desenho completo do fan-out. As sub-etapas E1–E4 e as Etapas A–D **não
> mudam**. A sub-etapa E5 original (eco de `plant_id` na resposta) foi **absorvida** pelo fan-out —
> todo item do envelope nomeia a usina sobre a qual agiu — e a antiga E6 (`is_default` em
> `GET /plants`) foi renumerada para E8.

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
| `alerts/router.py:31` `POST /alerts/run` | 409 | **fan-out**: roda em *todas* as usinas do escopo; envelope `{count, items}`, um item por usina |
| `climate/router.py:30` `POST /climate/collect` | 409 | **fan-out**: idem |
| `orchestration/router.py:34` `POST /pipeline/run` | 409 | **fan-out**: idem |
| `orchestration/router.py:171` `GET /pipeline/status/latest` | 409 | **fan-out**: idem; usina sem histórico vira `execution: null`, não 404 |

*(Nota factual: o prefixo real do router de orquestração é `/pipeline`, não `/orchestration` — `orchestration/router.py:21-24`. O texto do ADR usa os dois nomes; a rota é `POST /pipeline/run`.)*

**Correção de 2026-08-06 — o fan-out substitui o default nos quatro chamadores de execução/leitura acima.** A versão anterior desta seção aceitava rodar só a usina padrão e adiava o fan-out para uma "Etapa F". O usuário decidiu o contrário. Passa a valer a separação:

- **Chamadores de alvo único** (Telegram texto e PDF, `billing/intake-text`, `billing/pending`, `billing/confirm`, `billing/reject`): precisam escolher **uma** usina, e continuam resolvendo pelo `default_plant_id` (ou pelo `bill_id`, nos dois de billing). Escrever uma fatura em N usinas não faz sentido.
- **Chamadores de alvo múltiplo** (os quatro da tabela acima): a omissão de `plant_id` passa a significar "todas as usinas do escopo do principal", não "a usina padrão". Coletar clima ou rodar o pipeline em N usinas é exatamente o que se quer.

O `default_plant_id` **não participa** do fan-out. Desenho completo, contratos e riscos em § E.11.

### E.7 RLS, organizations e reviewer

- Toca `organizations` (coluna nova, escrita nova) e `plants` (leitura por organização) — **ambas sob RLS** (`db/rls_inventory.py:22`, migration `20260802_0040`).
- **Ponto a verificar antes de codar** (E1): o webhook do Telegram lê `OrganizationRecord` sob `set_platform_context` e só depois faz `set_tenant_context` (`telegram/router.py:136-139`). A escrita de `/usina` e a leitura do default precisam acontecer **sob `set_tenant_context(session, organization_id)`**, e é preciso confirmar que a política de `organizations` permite `UPDATE` da própria linha nesse contexto — caso contrário o comando falha em produção e passa em SQLite. Teste em PostgreSQL real é obrigatório, não opcional.
- `_infer_single_plant_for_organization` (sessão fresca) usa `set_organization_context`; a nova query cruza `organizations` com `plants`, **duas** tabelas sob RLS na mesma transação. Verificar que ambas as políticas aceitam o mesmo GUC de contexto.
- **Reviewer obrigatório nas sub-etapas E1, E2, E4 e E5** (`organizations`, migration, ingestão de faturas e o resolvedor de conjunto de usinas — E5 decide *quais* usinas um chamador toca, é código de isolamento). E3, E6, E7 e E8 não exigem reviewer; **E9 exige** (muda o que roda em produção de madrugada).

### E.8 Plano de implementação — nove sub-etapas verificáveis

*(Revisado em 2026-08-06. E1–E4 estão inalteradas. A antiga E5 — "eco de `plant_id`" — foi absorvida
pelo fan-out e não existe mais como item próprio. A antiga E6 — `is_default` em `GET /plants` — virou
E8. E5, E6, E7 e E9 são novas.)*

**E1 — migration, coluna e backfill.** *(CONCLUÍDA em 2026-08-05.)* `migrations/versions/20260805_0043_add_organization_default_plant.py`: coluna, FK `ON DELETE SET NULL`, backfill do parágrafo E.4, `downgrade` que dropa a coluna. Campo no `OrganizationRecord`. `PlantRepository.get_or_create` corrigido para receber e filtrar por `organization_id` e eleger o default quando a organização não tem nenhum. *Verificável*: `alembic upgrade head` e `downgrade -1` em PostgreSQL; teste que cria organização com 1 usina e vê `default_plant_id` preenchido; teste que cria a segunda usina e vê o default **inalterado**. **Reviewer.**

**E2 — resolvedor de alvo único.** Reescrever `_infer_single_plant_for_organization_in_session` com a ordem (a)–(d) de E.3.2, incluindo a revalidação por `JOIN`. A mensagem do 409 residual passa a citar `PATCH /organizations/{id}` com `default_plant_id`. **Esta função continua devolvendo *uma* usina — o fan-out não muda a forma dela** (ver E.11.3). *Verificável*: teste unitário das quatro ramificações, incluindo default apontando para usina de **outra** organização (deve ignorar o default e cair em (c)/(d), nunca vazar). **Reviewer.**

**E3 — comandos do bot e confirmação nomeada.** `/usinas`, `/usina <nome>`, `_pending_message` com nome da usina. *Verificável*: webhook com payload de comando troca o default e responde por `send_message` (client mockado); payload de fatura em org com 2 usinas responde `202` e grava na padrão; nome ambíguo não troca nada.

**E4 — `confirm`/`reject` derivam a usina do `bill_id`.** Remove `AdminPlant` dos dois handlers, troca por `AdminPrincipal` mais busca por `bill_id` mais `principal.require_plant_access(record.plant_id)`. *Verificável*: fatura de outra organização continua devolvendo **404**; confirmar sem `plant_id` numa org com 2 usinas funciona. **Reviewer.**

**E5 — resolvedor de conjunto (`ScopedPlantSet` / `AdminPlantFanout`).** Nova dependência em `core/tenancy.py`, ao lado de `resolve_admin_plant`, com a ordem de resolução e o teto de E.11.3. Entra aqui também o campo de configuração `fanout_max_plants`. **Nenhum handler muda nesta sub-etapa.** *Verificável sem tocar em endpoint*: teste de unidade cobrindo (a) `plant_id` explícito devolve conjunto de 1 com `explicit=True`; (b) principal de plataforma **nunca** faz fan-out (1 usina resolve, 2+ dá 409); (c) organização com 2 usinas devolve as 2, ordenadas por nome; (d) credencial `PlantScope.restricted({p2})` numa org `{p1,p2}` devolve só `p2`; (e) usina de outra organização nunca aparece; (f) escopo acima do teto dá 409 sem executar nada. **Reviewer.**

**E6 — expectativa de produção por usina.** `expected_daily_production_kwh` deixa de ser `Query(gt=0)` obrigatório em `alerts/run` e `pipeline/run` e passa a `Decimal | None`, resolvido por usina via `resolve_expected_daily_production` (`photovoltaic/read_service.py:348`, já existente) quando ausente. Matriz de comportamento em E.11.5. Fecha, para estes dois endpoints, a lacuna que o ADR-068 deixou aberta de propósito. *Verificável*: as quatro células da matriz de E.11.5 como teste de contrato; usina sem baseline devolve o `unavailable_reason` do ADR-068 e **não** dispara alerta.

**E7 — envelope e fan-out nos quatro handlers.** `alerts/run`, `climate/collect`, `pipeline/run` e `pipeline/status/latest` passam a usar `AdminPlantFanout`, respondem sempre `{count, succeeded, failed, skipped, items}`, com uma sessão e uma transação por usina, em laço sequencial. Depende de E5 e E6. *Verificável*: contrato por endpoint nos dois modos (explícito e fan-out), mais o teste de falha parcial de E.9.

**E8 — `is_default` em `GET /plants` e rótulo no seletor.** *(Era E6.)* Depende da Etapa A. *Verificável*: a listagem da organização traz `is_default: true` exatamente uma vez.

**E9 — fan-out do agendador (`cloud_jobs.py`).** *(Era a "Etapa F".)* `run_daily_pipeline`, `run_collection` e `run_operational_watchdog` deixam de resolver uma única usina por `MPLACAS_CLOUD_JOB_PLANT_NAME` e passam a iterar as usinas da organização, com a expectativa resolvida por usina (E6). **Sem esta sub-etapa o fan-out HTTP não faz a segunda usina ser coletada de madrugada** — ver E.11.7. Depende de E6. *Verificável*: job executado numa org com 2 usinas grava execução de pipeline para as duas; falha numa usina não impede a outra e o job termina com código de saída não-zero. **Reviewer.** **Entrada em escopo pende de confirmação — E.10 item 8.**

Ordem: E1, depois E2, depois E3 e E4 em paralelo. E5 vem depois de E2 (compartilham `core/tenancy.py`). E6 é independente e pode andar em paralelo com E2–E5. E7 depende de E5 e E6. E8 depende de A e de E1. E9 depende de E6.

### E.9 Critério de aceite

**Teste de aceite único, obrigatório, em PostgreSQL:** criar uma organização, criar **duas** usinas nela — `p1` (padrão) e `p2` — e, sem passar `plant_id` em lugar nenhum, exercitar **todos os nove chamadores** da tabela E.6: os oito HTTP mais o webhook do Telegram nos dois modos (texto e PDF). **Nenhum pode responder 409.** O critério, revisado em 2026-08-06, tem duas metades:

- **Alvo único** (Telegram texto, Telegram PDF, `billing/intake-text`, `billing/pending`, `billing/confirm`, `billing/reject`): agem sobre `p1` e **nomeiam a usina** na resposta.
- **Alvo múltiplo** (`alerts/run`, `climate/collect`, `pipeline/run`, `pipeline/status/latest`): respondem `count == 2` e o conjunto dos `plant_id` dos itens é exatamente `{p1, p2}`. **Verificação de efeito, não só de forma** — não basta o envelope citar as duas usinas: depois de `climate/collect` precisa existir observação climática **das duas** no intervalo pedido, e depois de `pipeline/run` precisa existir linha em `pipeline_executions` para **as duas**.

Complementos:

- **Falha parcial não derruba as demais**: com o provedor Open-Meteo forçado a falhar apenas para `p2`, `climate/collect` responde **200** com `succeeded == 1` e `failed == 1`, o item de `p2` traz `error.code`, e o dado de `p1` **está gravado** — prova de que há uma transação por usina, não uma transação para todas.
- **Isolamento**: organização B com usina `p3`; nenhuma resposta de A contém `p3`, e nenhum audit event gerado pelo fan-out de A referencia `p3`.
- **Principal de plataforma não faz fan-out**: chave estática operacional sem `plant_id` numa base com 2 usinas continua respondendo 409 — nunca "todas as usinas de todas as organizações".
- **Teto**: organização com `fanout_max_plants + 1` usinas responde 409 pedindo `plant_id`, **sem ter executado nenhuma usina**.
- **Compatibilidade single-plant**: com `plant_id=p2` explícito, `count == 1`, item de `p2`, e os códigos de erro de hoje preservados — 409 de pipeline já rodando, 422 de intervalo de datas inválido, 503 de Telegram não configurado, 404 de `status/latest` sem execução.
- Fatura enviada pelo Telegram numa org com 2 usinas cai na `default_plant_id`, e a mensagem de confirmação traz o nome dela.
- `/usina <outra>` seguido de nova fatura: a fatura vai para a outra usina.
- `PATCH /organizations/{id}` com `default_plant_id` de **outra** organização: 404, e o default não muda.
- `default_plant_id` apontando para usina removida: a FK zera o campo e o resolvedor de alvo único cai no fallback, sem 500. O fan-out é indiferente ao default.
- Credencial com `PlantScope.restricted({p2})` numa org cujo default é `p1`: nos chamadores de **alvo único** resolve para `p1` e então **404** em `require_plant_access` — falha fechada, sem vazamento; nos de **alvo múltiplo** o fan-out roda **só `p2`**, `count == 1`, sem erro. Escopo restrito deixa de ser um caso de erro nos quatro endpoints de execução.
- Organização com **zero** usinas: continua 409 nos dois modos, agora com mensagem acionável. Correto, não há o que resolver.

### E.10 Pontos de confirmação do usuário

*(Revisado em 2026-08-06.)*

**Resolvidos:**

1. ~~Fan-out não entra nesta etapa.~~ **REVOGADO em 2026-08-06 por decisão explícita do usuário: o fan-out foi promovido para dentro da Etapa E.** A redação original registrava como limitação aceita que `alerts/run`, `climate/collect` e `orchestration/run` sem `plant_id` rodariam só na usina padrão, adiando o fan-out para uma "Etapa F". Passa a valer o desenho da § E.11: esses endpoints rodam em **todas** as usinas do escopo do principal e respondem em lista. A "Etapa F" deixa de existir como etapa futura e vira a sub-etapa **E9** (fan-out do agendador), dentro deste ADR.
2. **FK simples vs. FK composta** — confirmada a simples, com revalidação no read (E.3.2). Já implementada em E1.
3. **Mudança de comportamento do bot em produção** — confirmada.
4. **`PlantRepository.get_or_create` corrigido dentro de E1** — confirmado e implementado.

**Abertos, introduzidos pelo fan-out (precisam de confirmação antes de E7):**

5. **Envelope uniforme mesmo quando `plant_id` é explícito.** Os quatro endpoints passam a responder `{count, items}` **sempre**, inclusive no caso de uma usina só — a resposta de hoje vira o corpo do item único. Verificado que nenhum chamador automatizado quebra: o Cloud Scheduler não fala HTTP com esses endpoints (§ E.11.1, achado A), o frontend não os chama (nenhuma ocorrência em `frontend/src/**`), o Telegram não os chama; só os testes de contrato. Mesmo assim, é mudança de contrato público. A alternativa é resposta **polimórfica** (objeto quando `plant_id` é explícito, lista quando omitido) — rejeitada por custo permanente em OpenAPI, em tipos de cliente e em todo teste futuro. **Confirmar o envelope uniforme.**
6. **`expected_daily_production_kwh` deixa de ser obrigatório** em `alerts/run` e `pipeline/run` e passa a ser derivado no servidor quando ausente (§ E.11.5). Se o valor derivado divergir do que vem sendo passado à mão ou por env, **a severidade dos alertas em produção muda**. É a consequência inevitável do fan-out: um único valor de query string não descreve N usinas de portes diferentes. **Confirmar.**
7. **Falha parcial responde 200.** Um `pipeline/run` em que uma de duas usinas falhou devolve **200** com `failed == 1`, não 5xx. Quem monitora por código de status precisa passar a olhar o corpo (ou os audit events por usina, que continuam sendo gravados com `outcome="failure"`). Alternativa considerada e rejeitada: 207 Multi-Status (§ E.11.2). **Confirmar.**
8. **E9 (fan-out do agendador) entra em escopo?** Sem ela, o fan-out HTTP fica pronto mas **a segunda usina continua sem coleta noturna**, porque o Cloud Run Job resolve uma única usina por `MPLACAS_CLOUD_JOB_PLANT_NAME`. Recomendo que entre, depois de E6. **Confirmar.**

---

### E.11 Fan-out de execução em múltiplas usinas (decisão de 2026-08-06)

Esta seção substitui a limitação registrada em § E.6 e § E.10 item 1 na versão de 2026-08-05. Ela decide **o que** os endpoints de execução fazem quando `plant_id` é omitido numa organização com N usinas, e é a única parte da Etapa E que muda contrato público.

#### E.11.1 Quatro achados que definem o desenho

**A. O Cloud Scheduler não chama esses endpoints.** `infra/gcp/provision-operations.sh` cria jobs do Cloud Scheduler cujo `--uri` é `https://<região>-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/<projeto>/jobs/<nome>:run` — isto é, o agendador dispara um **Cloud Run Job**, não o serviço HTTP. O job executa `python -m mplacas.cloud_jobs daily-pipeline` (`--args=-m,mplacas.cloud_jobs,<comando>`), e `cloud_jobs.run_daily_pipeline` chama `run_ledger_backed_daily_pipeline` **em processo**, com `plant_id` resolvido de `MPLACAS_CLOUD_JOB_PLANT_NAME` sob `DEFAULT_ORGANIZATION_ID` (`cloud_jobs.py:404` e `_resolve_plant_id`, `cloud_jobs.py:561-577`). Busca em `frontend/src/**` e em `src/mplacas/telegram/**` não encontra nenhuma chamada a `alerts/run`, `climate/collect` ou `pipeline/run`: os únicos chamadores desses caminhos no repositório são testes. **Duas consequências:** (i) a mudança de contrato HTTP tem impacto **zero** no agendador; (ii) o fan-out HTTP **não** resolve a automação noturna — daí a sub-etapa E9.

**B. Os dois limites de tempo são diferentes por uma ordem de grandeza.** O serviço HTTP roda com `GCP_REQUEST_TIMEOUT=60` segundos (`infra/gcp/config.env:13`; o teto validado em `infra/gcp/lib.sh:205` é 300). O Cloud Run Job roda com `--task-timeout 30m`. Fan-out síncrono dentro de um handler HTTP precisa, portanto, de **teto explícito de usinas**; fan-out dentro do job, não.

**C. `expected_daily_production_kwh` é hoje obrigatório e é específico da usina.** Em `alerts/router.py:32` e `orchestration/router.py:36` ele é `Query(gt=0)`, sem default. **Um único valor não descreve N usinas de portes diferentes.** Aplicar a expectativa da usina A à usina B produziria severidade errada e dispararia alerta errado no Telegram — exatamente a classe de corrupção silenciosa que § E.1 identificou no caminho de faturas. O ADR-068 deliberadamente não tocou nesses dois endpoints; o fan-out obriga a fechar essa lacuna. O custo é baixo: `resolve_expected_daily_production` (`photovoltaic/read_service.py:348`) já existe, já resolve por usina e, conforme seu próprio docstring, não acrescenta query alguma além das que `get_latest_performance` e `get_latest_baseline` já rodam.

**D. `PlantScope` não delimita organização.** A chave operacional estática da plataforma carrega `PlantScope.unrestricted()` (`core/authorization.py:16-17`), que `allows()` qualquer usina. Fan-out derivado do `plant_scope` sozinho rodaria **todas as usinas de todas as organizações**. O conjunto do fan-out precisa nascer de uma query por `organization_id` e só então ser intersectado com o escopo.

#### E.11.2 Contrato: envelope uniforme, códigos de status preservados no modo explícito

Regra única, aplicável aos quatro endpoints (`POST /alerts/run`, `POST /climate/collect`, `POST /pipeline/run`, `GET /pipeline/status/latest`):

> **A forma é sempre o envelope `{count, succeeded, failed, skipped, items}`.** Os **códigos de status** são exatamente os de hoje quando `plant_id` é explícito. Quando `plant_id` é omitido, o erro de uma usina vira dado dentro do item dela e **nunca** derruba as demais.

Envelope, no padrão `{count, items}` já usado por `list_organizations`, `list_invitations` e `GET /plants` (§ 4):

```jsonc
{
  "count": 2,
  "succeeded": 1,
  "failed": 1,
  "skipped": 0,
  "items": [
    {
      "plant_id": "…uuid p1…",
      "plant_name": "Matriz — Telhado A",
      "outcome": "succeeded",
      "error": null,
      "result": { /* exatamente o corpo que o endpoint devolve hoje, sem o plant_id duplicado */ }
    },
    {
      "plant_id": "…uuid p2…",
      "plant_name": "Filial Norte",
      "outcome": "failed",
      "error": { "code": "OPEN_METEO_PROVIDER_ERROR", "message": "weather provider is unavailable or returned invalid data" },
      "result": null
    }
  ]
}
```

- `outcome` ∈ `succeeded` | `failed` | `skipped`. `skipped` cobre o caso legítimo de "não havia o que fazer nesta usina" — hoje o único é a usina sem expectativa de produção derivável (§ E.11.5); não é erro e não deve inflar `failed`.
- `error.code` é o nome da exceção normalizado (`type(exc).__name__.upper()`), o mesmo identificador que os handlers já emitem em log estruturado hoje (`climate/router.py:79`, `orchestration/router.py:118`). `error.message` é a mensagem já sanitizada que o handler devolveria no `detail` do HTTPException correspondente. **Nenhuma mensagem nova de erro é inventada.**
- `plant_name` está no item porque é o que faz um humano lendo a saída de um `curl` saber sobre o que agiu. Ele substitui o "eco de `plant_id`" da antiga sub-etapa E5, que fica absorvida.
- Ordenação dos itens: por `Plant.name`, desempate por `Plant.id` — determinística, para o teste de aceite poder comparar listas.

**Código de status no modo fan-out: sempre 200, inclusive em falha parcial.** Mapear N erros heterogêneos num único código é lossy, e qualquer código de erro convida a um retry que re-executaria as usinas que deram certo. A visibilidade da falha vem de três lugares que já existem: o campo `failed` no topo, um audit event **por usina** com `outcome="failure"` (padrão já presente nos três handlers) e o log estruturado por usina. Considerado e rejeitado: **207 Multi-Status** — comunica melhor, mas é semanticamente WebDAV, não tem tratamento padrão em cliente HTTP nenhum do projeto e obrigaria todo teste a distinguir 200 de 207 sem ganho operacional. Ponto de confirmação § E.10 item 7.

**Modo explícito (`plant_id` presente) preserva integralmente os códigos de hoje**, porque o erro de uma única usina é o erro da requisição: 409 de `PipelineExecutionAlreadyRunningError`, 422 de `ClimateCollectionError` e de `ValueError`, 502 de `OpenMeteoProviderError` e de falha de pipeline, 503 de Telegram não configurado, 404 de `status/latest` sem execução, 404 de `plant_id` fora do escopo.

**Erros de requisição continuam sendo códigos HTTP nos dois modos**, porque não pertencem a nenhuma usina: 422 de validação de `start_date`/`end_date`, 503 de Telegram não configurado, 409 de escopo (vazio, acima do teto, ou principal de plataforma), 404 de `plant_id` fora do escopo.

**`GET /pipeline/status/latest`**: no modo fan-out, usina sem histórico de execução vira item com `outcome: "skipped"` e `result: null`, **não** 404 — a pergunta "qual o estado de todas" tem resposta mesmo quando uma delas nunca rodou. No modo explícito, o 404 de hoje é preservado.

#### E.11.3 Resolvedor: uma função irmã, e o resolvedor de E2 não muda de forma

Decisão: **`_infer_single_plant_for_organization_in_session` continua devolvendo exatamente uma usina.** Ela não passa a devolver lista quando `plant_id` é ausente. A razão é que os dois grupos de chamadores querem coisas semanticamente diferentes, e uma função que devolve "uma ou muitas" obrigaria cada um dos nove chamadores a decidir o que fazer com o caso que não lhe interessa — inclusive os de escrita de fatura, onde "muitas" seria um bug de atribuição de dado.

Entra uma **função irmã**, ao lado, em `core/tenancy.py`:

```python
@dataclass(frozen=True, slots=True)
class ScopedPlantSet:
    plant_ids: tuple[uuid.UUID, ...]   # ordenado por Plant.name, desempate por Plant.id
    principal: OperationsPrincipal
    explicit: bool                     # True quando o chamador passou plant_id

async def resolve_admin_plant_fanout(
    principal: Annotated[OperationsPrincipal, Depends(_admin_principal)],
    plant_id: uuid.UUID | None = Query(default=None),
) -> ScopedPlantSet: ...

AdminPlantFanout = Annotated[ScopedPlantSet, Depends(resolve_admin_plant_fanout)]
```

Ordem de resolução:

- **(a) `plant_id` explícito** — `principal.require_plant_access(plant_id)`; devolve `(plant_id,)` com `explicit=True`. Idêntico ao que `resolve_admin_plant` faz hoje.
- **(b) omitido e `principal.organization_id is None`** (chave estática de plataforma) — **nunca faz fan-out**. Cai no comportamento de hoje, `_infer_single_plant_for_organization(None)`: uma usina resolve, duas ou mais dão 409. Isso preserva o caminho da chave estática em instalação de uma usina e fecha o achado D — a chave de plataforma jamais atravessa organizações.
- **(c) omitido com organização** — `select(Plant.id, Plant.name).where(Plant.organization_id == principal.organization_id).order_by(Plant.name, Plant.id)`, resultado filtrado por `principal.plant_scope.allows(...)`. Conjunto vazio: **409** com a mensagem acionável de E2. Conjunto acima do teto: **409** pedindo `plant_id` explícito.

**`default_plant_id` não participa do fan-out.** Ele continua sendo a resposta dos chamadores de alvo único (Telegram, `billing/intake-text`, `billing/pending`). Uma usina padrão existe para responder "onde lanço esta fatura", não "quais usinas devo coletar". As duas perguntas coexistem com resolvedores próprios, e nenhuma sub-etapa de E1 a E4 muda por causa disso.

**Teto**: `settings.fanout_max_plants`, default **10**, derivado do achado B — 60 segundos de timeout HTTP e alguns segundos por usina em `pipeline/run` (busca no Open-Meteo mais envio no Telegram) não comportam muito mais. Estourar o teto **falha fechado antes de executar qualquer usina**, em vez de estourar o timeout no meio do laço e deixar escritas parciais sem resposta ao chamador. Quando uma organização real passar do teto, a saída correta é E9 (rodar no job, com 30 minutos), não aumentar o número.

#### E.11.4 Execução: sequencial, uma sessão e uma transação por usina

Sequencial, **não** `asyncio.gather`. Quatro razões: o contexto de tenant é um GUC por conexão e compartilhar sessão entre tarefas concorrentes não é seguro; Open-Meteo e a API do Telegram têm limite de taxa; o pool de conexões é dimensionado para requisições, não para N execuções simultâneas por requisição; e a ordem determinística é o que torna o teste de aceite verificável.

Por usina, dentro do laço:

```python
for plant_id in scoped.plant_ids:
    scoped.principal.require_plant_access(plant_id)      # asserção defensiva
    async with SessionFactory() as session:              # sessão nova por usina
        await set_principal_context(session, scoped.principal)
        ...                                               # trabalho + audit event
        await session.commit()
```

A troca em relação a hoje é que a sessão passa a ser aberta **dentro** do laço, não fora. Isso é o que dá isolamento de falha: um `rollback` provocado pela usina B não descarta o trabalho nem o audit event já commitados da usina A. No modo explícito o laço tem uma iteração só e a exceção é **relançada** como o `HTTPException` de hoje, em vez de capturada; no modo fan-out ela é capturada e vira o `error` do item.

#### E.11.5 Expectativa de produção por usina (pré-requisito do fan-out, não acessório)

`expected_daily_production_kwh` passa a `Decimal | None = Query(default=None, gt=0)` em `alerts/run` e `pipeline/run`. Matriz completa:

| `plant_id` | `expected_daily_production_kwh` | Efeito |
|---|---|---|
| explícito | presente | **Comportamento de hoje, byte a byte.** Nada muda. |
| explícito | ausente | Deriva por `resolve_expected_daily_production`. Indisponível: **422** com o `unavailable_reason` do ADR-068 (`NO_PERFORMANCE_HISTORY`, `REFERENCE_YEAR_INCOMPLETE`, `INSUFFICIENT_SEASONAL_SAMPLES`, `INCOMPLETE_EXPECTATION_INPUTS`). |
| omitido | presente | **409.** Uma expectativa única não descreve N usinas — passe `plant_id` ou omita o parâmetro. Falha fechada, e é o ponto que impede a corrupção descrita no achado C. |
| omitido | ausente | Deriva **por usina**. Usina sem expectativa derivável vira item `outcome: "skipped"` com `reason` = o código de indisponibilidade, sem alerta enviado. |

`expected_cycle_production_kwh` recebe o mesmo tratamento: já é opcional, e no modo fan-out ser passado dá 409 pela mesma razão.

`climate/collect` não tem parâmetro dependente de usina — `start_date` e `end_date` valem igualmente para todas — e portanto não é afetado por esta subseção.

Isto fecha, para `alerts/run` e `pipeline/run`, a lacuna que o ADR-068 deixou aberta explicitamente ("não toca em `POST /alerts/run` nem em `POST /orchestration/run`"). Como a derivação pode divergir do valor que vem sendo passado à mão, é ponto de confirmação (§ E.10 item 6).

#### E.11.6 Isolamento multi-tenant

O que garante que o fan-out não vaza entre organizações, em cinco pontos verificáveis:

1. O conjunto nasce de `Plant.organization_id == principal.organization_id`, **nunca** do `plant_scope` sozinho (achado D). Sem `organization_id`, não há fan-out (ramo (b)).
2. O conjunto é intersectado com `principal.plant_scope.allows(...)`, preservando credencial persistida com escopo restrito (ADR-043) — mesma regra do filtro duplo de `GET /plants` (§ 3).
3. `set_principal_context(session, principal)` é chamado por sessão, uma vez por usina. Como todas as usinas do laço pertencem à mesma organização por construção de (c), **o GUC de organização é o mesmo do início ao fim** — o desenho nunca troca de contexto de tenant no meio de uma transação, que seria o vetor de vazamento mais provável.
4. `principal.require_plant_access(plant_id)` é repetido dentro do laço, como asserção defensiva, mesmo já tendo sido aplicado na montagem do conjunto.
5. `plants` está sob RLS por `organization_id` (migration `20260802_0040`), o que faz o passo 1 ser defesa em profundidade, não a única barreira.

Teste obrigatório correspondente em § E.9: organização A com `p1`/`p2` e organização B com `p3`; o fan-out de A produz exatamente dois itens, nenhuma resposta contém `p3`, e nenhum audit event gerado por A referencia `p3`.

#### E.11.7 Agendador: nada a mudar para o contrato HTTP, e uma lacuna separada a fechar

**Para o contrato novo funcionar, `cloud_jobs.py` não precisa mudar nada** — o agendador não fala HTTP com esses endpoints (achado A). Entre as duas opções pedidas, a recomendação é **fan-out dentro do próprio handler: uma chamada HTTP, N execuções internas, sequenciais, com teto**. É a opção com menos partes móveis, não quebra nenhum chamador automatizado (não existe nenhum) e não exige inventar um cliente HTTP no agendador que hoje não existe. Fazer o laço do lado do agendador significaria escrever esse cliente, dar-lhe credencial, retry e observabilidade próprios — custo alto para resolver um problema que o handler resolve com um `for`.

Mas o agendador tem **a mesma lacuna, no lugar dele**: `run_daily_pipeline`, `run_collection` e `run_operational_watchdog` resolvem uma única usina por `MPLACAS_CLOUD_JOB_PLANT_NAME` sob `DEFAULT_ORGANIZATION_ID`. **Fan-out HTTP não faz a segunda usina ser coletada de madrugada.** Fechar isso é a sub-etapa **E9**, e o job é o lugar certo para fazê-lo: `--task-timeout 30m` contra os 60 segundos do serviço, sem teto de usinas necessário. E9 depende de E6, porque `MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH` é um valor único de ambiente e sofre exatamente do problema do achado C.

#### E.11.8 Consequências desta correção

**Positivas.** A segunda usina passa a ser operável de fato, não apenas visível na interface. A restrição de escopo (`PlantScope.restricted`) deixa de ser um caso de erro nesses quatro endpoints e passa a ser simplesmente um conjunto menor. E o fan-out força o fechamento da lacuna do ADR-068 em `alerts/run` e `pipeline/run`, que ficaria aberta indefinidamente.

**Negativas.** Contrato público muda (§ E.10 item 5). Falha parcial responde 200 e exige leitura do corpo (§ E.10 item 7). A severidade dos alertas em produção pode mudar (§ E.10 item 6). Surge um teto artificial de usinas por requisição, consequência direta do timeout de 60 segundos; a saída estrutural para organizações grandes é E9, não aumentar o teto. E a Etapa E, que era de superfície mais uma coluna, passa a incluir um resolvedor de isolamento novo — daí o reviewer obrigatório em E5.

**Reversibilidade.** Média, menor que a das Etapas A–D. O envelope é uma mudança de contrato: reverter exige voltar os quatro handlers e os testes de contrato. Nada disso envolve migração de dados — a correção não acrescenta nem altera coluna alguma.
