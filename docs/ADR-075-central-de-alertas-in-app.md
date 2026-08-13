# ADR-075 — Central de alertas in-app: não construir agora

## Status

**Proposto** (2026-08-13). Base: `HEAD 15fa2f6`.
Tarefa **T3** de `docs/PLANO_EXECUCAO_AUDITORIA_FRONTEND_2026-08-12.md` — a tarefa que o próprio
plano classificou como a mais cara (§2.6, 6ª e última na ordem de valor/esforço).

⚠ **Working tree não estava limpo na emissão deste ADR.** `git status --short` mostrava
`src/mplacas/intelligence/anomaly_service.py` e `src/mplacas/intelligence/router.py` modificados
(T7 em andamento: mover o cálculo de rendimento do frontend para o backend). Este ADR **leu a
versão da working tree** desses dois arquivos e **não os altera**. A Decisão 4 depende de um
campo que a T7 não toca (`daily[].diagnostics`), então as duas tarefas não colidem — mas quem
implementar deve reconfirmar após a T7 fechar.

**A recomendação deste ADR é recusar o escopo original da T3.** Isso contraria a lista de
tarefas do plano e por isso está marcado **⚠ CONFIRMAR** na Decisão 1. As Decisões 2, 3 e 9
também exigem confirmação. O restante é derivado.

## Contexto

### O que a T3 afirmou, e o que a verificação encontrou

O plano descreveu o estado assim (§3, T3):

> "a única tabela de alerta é `alert_delivery_records` (…) **o conteúdo do alerta não é
> persistido**. Não há severidade, nem texto, nem causa, nem qual inversor — nada disso sobrevive
> ao envio."

**A primeira frase está correta. A segunda está errada**, e é justamente a que define o custo da
tarefa. O conteúdo do alerta **é** persistido — em `outbox_events`, não em `alerts/`.

| Fato | Evidência |
|---|---|
| `alerts/router.py` expõe só `POST /run` | `src/mplacas/alerts/router.py:56` |
| `AlertDeliveryRecord` guarda apenas `plant_id`, `fingerprint`, `provider`, `destination_ref`, `sent_at`, com unique `(plant_id, fingerprint)` | `src/mplacas/alerts/db_models.py:14-29` |
| **Todo alerta despachado grava título, mensagem, severidade, ação recomendada e `occurred_at` em `outbox_events.payload_json`** | `src/mplacas/alerts/outbox.py:71-91` |
| Esse payload é um `AlertCandidate` completo e reconstruível — `_deserialize_alert` o desserializa de volta no despacho | `src/mplacas/alerts/outbox.py:245-270`; dataclass em `src/mplacas/alerts/models.py:27-46` |
| O payload tem integridade verificada por SHA-256 na leitura (falha vira `OutboxEventIntegrityError`) | `src/mplacas/events/db_models.py:51-52`; `src/mplacas/events/outbox.py:57-66` |
| `outbox_events` já tem `plant_id` FK não-nulo e índice `(plant_id, created_at)` | `src/mplacas/events/db_models.py:29,42-45` |
| `outbox_events` **já está sob RLS** por `plant_id` | `src/mplacas/db/rls_inventory.py:35`; `migrations/versions/20260802_0040_enable_postgresql_rls.py:41` |

Ou seja: **a decisão central que o plano pediu — "persistir o conteúdo (modelo novo + migration)
versus recalcular sob demanda" — parte de uma premissa falsa.** Existe uma terceira opção que já
está implementada e em produção há tempo: o conteúdo está gravado, íntegro, escopado por usina e
isolado por RLS. Nenhuma migration é necessária para ter fidelidade ao que foi enviado.

Isso muda o cálculo de custo da tarefa, mas **não** é suficiente para justificá-la. O resto deste
Contexto explica por quê.

### Quais alertas existem de fato em produção

`build_alert_candidates` produz **exatamente dois** tipos (`src/mplacas/alerts/candidates.py:91-102`):

| Alerta | `message` vem de | Evidência |
|---|---|---|
| Executivo | `dashboard.headline` | `src/mplacas/alerts/candidates.py:37-46` |
| Anomalia | `diagnostic.message` do pior dia avaliado da janela | `src/mplacas/alerts/candidates.py:63-88` |

E o alerta **por inversor** — o que motivou a ADR-074, com `_device_lines` renderizando HTML de
Telegram — **não tem caller de produção nenhum**. `send_production_alert`
(`src/mplacas/alerts/production_alert.py:392`) é referenciado somente por
`tests/test_production_alert.py:29,473,500,528,541`. Nenhum router, job, pipeline ou entrypoint
o invoca (`grep -rn "send_production_alert" --include=*.py .` → só essas linhas).

Consequência direta: **uma "central de alertas" hoje não teria um único alerta por inversor para
mostrar.** A informação mais valiosa que existe sobre equipamento já foi exposta pela T1/ADR-074,
por endpoint de leitura próprio, sem passar por alerta nenhum.

### Para quem os alertas são enviados hoje

O destino é um **único chat global de processo**, não um chat por cliente:

- `telegram_alert_chat_id` é `Settings`, valor único de ambiente (`src/mplacas/core/config.py:57`).
- O job diário lê esse valor uma vez e usa para todas as usinas
  (`src/mplacas/cloud_jobs.py:477-480`, `:491-494`), derivando `destination_ref` de um hash dele
  (`src/mplacas/alerts/router.py:28-30`).
- O job diário itera apenas as usinas de `DEFAULT_ORGANIZATION_ID` (`src/mplacas/cloud_jobs.py:497`).
- Em contraste, a **entrada** de fatura por Telegram já é por organização
  (`OrganizationRecord.telegram_chat_id`, `src/mplacas/organizations/db_models.py:29`, resolvida em
  `src/mplacas/telegram/router.py::_resolve_telegram_organization`).

Portanto a frase do plano *"quem não usa o bot não vê alerta nenhum"* é otimista demais quanto ao
canal existente. O correto é: **nenhum cliente recebe alerta hoje.** O canal de alerta é do
operador da plataforma, não do usuário final. Não existe um "alerta que o usuário recebeu no
Telegram" com o qual um histórico in-app pudesse concordar ou discordar — o dilema de fidelidade
que a T3 levanta ("recalcular hoje pode devolver resultado diferente do que o usuário recebeu")
**não tem sujeito** no produto atual.

### O que a interface já mostra — e onde uma central de alertas se sobreporia

| Superfície | O que mostra | Origem |
|---|---|---|
| `DiagnosticsCard` (Visão Geral) | Lista de diagnósticos do ciclo + tendência, com severidade e ação recomendada. Estado vazio literalmente diz **"Sem alertas"** | `frontend/src/components/DiagnosticsCard.tsx:15,34-57`; dados de `combineDiagnostics` (`frontend/src/lib/dashboard/contracts.ts:185-186`) |
| `AttentionSummary` (chip no `HeroCard`) | Contagem de críticos + âncora para a lista | `frontend/src/components/AttentionSummary.tsx:11-31` |
| `ProductionDiagnosticPanel` (Produção) | Diagnóstico do período, pior dia, perda estimada, sequência, playbook, **e um chip "Critério de alerta"** | `frontend/src/components/ProductionDiagnosticPanel.tsx:243-284,415-425` |
| `TechnicalDiagnosticPanel` (Técnico) | Diagnóstico da modelagem fotovoltaica | `frontend/src/pages/dashboard/TechnicalPage.tsx:235` |
| `DeviceStatusSection` (Técnico) | Estado por inversor, com `yield_status` | ADR-074, Decisão 5 |

Os dois alertas que existem são construídos **a partir dos mesmos objetos que essas telas já
exibem**: o executivo copia `dashboard.headline` (`candidates.py:41-44`), que o `HeroCard` mostra;
o de anomalia copia `diagnostic.message`/`recommended_action` do pior dia (`candidates.py:74-86`),
que é a mesma família de diagnóstico do `DiagnosticsCard`.

Uma central de alertas mostraria, como "alerta", texto que o usuário já lê como "diagnóstico" —
na mesma sessão, muitas vezes na mesma tela. **O valor incremental não está no conteúdo. Está
apenas no eixo do tempo.**

### O eixo do tempo já está no navegador, e é descartado

`GET /energy/anomalies/latest` já devolve, **por dia**, ao longo de até 90 dias:

```jsonc
{ "date": "…", "level": "CRITICAL", "deviation_percent": "-52.0",
  "diagnostics": [ { "code": "…", "level": "…", "message": "…", "recommended_action": "…" } ] }
```

Evidência: `src/mplacas/intelligence/router.py:150-189` (o array `diagnostics` está em `:174-186`);
limite `days` de 1 a 90 em `:322`.

E o frontend **já pede 90 dias**: `fetchAnomalyHistory(plantId, days = 90)`
(`frontend/src/lib/api.ts:72-74`).

E o parser **joga o array fora**: `AnomalyDailyPoint` não tem o campo
(`frontend/src/lib/dashboard/contracts.ts:111-125`) e `parseAnomalyDaily` não o lê
(`frontend/src/lib/dashboard/contracts.ts:326-336`).

**Noventa dias de histórico de severidade diária, com mensagem e ação recomendada, já trafegam
pela rede em toda abertura do módulo Produção e são silenciosamente descartados no cliente.**
Este é o achado mais importante deste ADR. Ele torna o custo do valor real da T3 quase nulo — e
torna qualquer migration desproporcional.

### Já existem quatro taxonomias de severidade concorrentes na tela

1. `DiagnosticSeverity` do executivo (INFO/WARNING/CRITICAL) — `DiagnosticsCard`.
2. `AnomalyLevel` por dia (NORMAL/ATTENTION/ANOMALY/CRITICAL) — `contracts.ts:108-109`.
3. **Um motor de alerta próprio, no cliente**, com limiares e rótulos próprios
   ("Alerta crítico"/"Atenção"/"Dentro do gatilho"), calculado 100% no navegador:
   `frontend/src/lib/dashboard/production-alerts.ts:10-13` (`EXPECTED_WARNING_THRESHOLD_PERCENT = 85`,
   `EXPECTED_CRITICAL_THRESHOLD_PERCENT = 75`, `HISTORICAL_WARNING_DROP_PERCENT = -15`,
   `HISTORICAL_CRITICAL_DROP_PERCENT = -25`) e `:188-247` (`productionAlertSignal`), renderizado como
   "Critério de alerta" em `ProductionDiagnosticPanel.tsx:415-425`.
4. `yield_status` por inversor (NORMAL/DROPPED/UNKNOWN) — ADR-074.

O item 3 é, além de uma taxonomia extra, uma violação da regra 0.3.3 do plano (limiar de
severidade vivendo no frontend) da mesma família que a T7 está corrigindo em `yield.ts`.

**Uma "central de alertas" seria a quinta superfície de severidade do produto.** O risco de fadiga
de alarme aqui não é volume de linhas; é **veredictos que discordam entre si na mesma sessão** —
o usuário lê "Sem alertas" no `DiagnosticsCard`, "Atenção" no chip de critério de alerta, e uma
central que diz uma terceira coisa. Isso não cansa: confunde, e destrói a confiança que o produto
inteiro depende de manter.

### Restrições que qualquer solução teria de respeitar

1. **Convenção de leitura:** 200 sempre dentro do escopo, indisponibilidade como campo + motivo
   (plano §2.2; padrão em `src/mplacas/photovoltaic/router.py:112-122`). Exceção herdada e
   conhecida: `/energy/anomalies/latest` ainda devolve 404 quando não há dado
   (`src/mplacas/intelligence/router.py:339-340`) — o frontend já trata (`anomalyState.error === 'NOT_FOUND'`,
   `ProductionDiagnosticPanel.tsx:213`).
2. **Isolamento multi-tenant:** `set_principal_context` obrigatório em qualquer handler novo.
3. **Nenhum cálculo energético/financeiro novo no frontend** (regra 0.3.3).
4. **Severidade nunca só por cor:** cor + texto + ícone (plano §3, T3).
5. **Nenhuma dependência de runtime nova** (regra 0.3.5).

## Decisão

### 1. Não construir uma central de alertas como superfície própria — ⚠ CONFIRMAR

Não haverá rota, aba, sino, badge, drawer ou página "Alertas". Não haverá endpoint
`GET /alerts/*` de leitura. Não haverá tabela nova.

Os quatro motivos, em ordem de força, todos verificados acima:

1. **O conteúdo seria redundante.** Os dois únicos alertas existentes são derivados de
   `dashboard.headline` e de `diagnostic.message` (`candidates.py:41-44,74-86`) — texto que
   `DiagnosticsCard` e `ProductionDiagnosticPanel` já exibem.
2. **O canal atual não é do cliente.** O destino é um chat global de processo
   (`core/config.py:57`, `cloud_jobs.py:477-480`) e o job só roda para `DEFAULT_ORGANIZATION_ID`
   (`cloud_jobs.py:497`). Não existe "o alerta que o usuário recebeu" a espelhar.
3. **Seria a quinta taxonomia de severidade na tela**, com três das quatro atuais já discordando
   entre si.
4. **O valor real — o eixo temporal — já está no cliente e é descartado**
   (`intelligence/router.py:174-186` → `api.ts:72-74` → `contracts.ts:326-336`).

**Isto contradiz a lista de tarefas do plano.** A T3 permanece aberta no plano até o usuário
confirmar esta recusa. Se a confirmação não vier, a Decisão 9 descreve o caminho a seguir.

### 2. A pergunta "persistir × recalcular" é respondida por "já está persistido" — ⚠ CONFIRMAR

Registra-se formalmente, para que a questão não seja reaberta do zero:

| Caminho | Veredito | Motivo |
|---|---|---|
| **(A) Modelo novo + migration** (persistir conteúdo em tabela de alertas) | **Recusado** | Duplicaria estado que `outbox_events.payload_json` já guarda com integridade verificada (`events/outbox.py:57-66`). Custo detalhado na Decisão 9 |
| **(B) Recalcular sob demanda na leitura** | **Recusado como conceito, já implementado como fato** | Para o alerta de anomalia, "recalcular" é literalmente o que `analyze_recent_persisted_anomalies` faz a cada chamada de `/energy/anomalies/latest`. Construir uma segunda superfície que recalcula o mesmo seria duplicação pura |
| **(C) Ler `outbox_events` filtrando `event_type = 'alert.delivery.requested'`** (`alerts/outbox.py:21`) | **Tecnicamente viável, recusado por valor** | Sem migration, sem schema, RLS já ativa. É o caminho pré-decidido para o futuro (Decisão 9), não para agora — ver as três limitações abaixo |
| **(D) Expor o histórico diário que já chega ao cliente** | **Escolhido** (Decisão 4) | Zero backend, zero migration, zero endpoint |

**As três limitações que desqualificam (C) hoje** — todas verificadas, e todas relevantes para
quem reabrir a decisão:

1. **Retenção de 30 dias, e ela apaga o histórico.** `RetentionService` deleta `outbox_events`
   com status DELIVERED/FAILED mais velhos que `outbox_events_days`
   (`src/mplacas/retention/service.py:121-132`), default 30 (`:50`, e
   `src/mplacas/core/config.py:80`). É a janela mais curta entre as tabelas operacionais — o
   ledger de dedupe, por comparação, guarda 365 dias (`retention/service.py:52`), com justificativa
   explícita no docstring (`:39-46`). Um histórico de alertas construído sobre uma fila cujo
   propósito declarado é ser esvaziada é acoplamento semântico errado.
2. **A fila repete o mesmo incidente.** O fingerprint de anomalia inclui `end_date`
   (`alerts/candidates.py:79-82`) e `worst_level` é calculado sobre a janela inteira
   (`intelligence/anomaly_service.py:282-283`). Com `anomaly_days = 7`
   (`orchestration/daily_pipeline.py:66`), **um único dia ruim gera um fingerprint novo por dia
   durante 7 dias** — 7 linhas de outbox, 7 mensagens de Telegram. Um histórico fiel à fila
   mostraria 7 "alertas" onde houve 1 incidente. Isso é a definição operacional de fadiga de
   alarme, e viria de graça junto com a fidelidade.
3. **A fila é do destino, não do usuário.** `deduplication_key` e `destination_ref` embutem o hash
   do chat de Telegram (`alerts/outbox.py:77-79`; `alerts/router.py:28-30`). Trocar ou remover o
   chat muda a chave e, portanto, o histórico. Um histórico de produto não pode depender da
   configuração de um canal de notificação.

**O que (C) tem de bom, e que deve ser preservado como conhecimento:** severidade abaixo do mínimo
**nunca** entra na fila (`alerts/outbox.py:58-70`, com `minimum_severity = WARNING` no job diário,
`cloud_jobs.py:549`). A fila já é um fluxo pré-filtrado de WARNING+ — a melhor defesa contra fadiga
de alarme que o projeto tem hoje, e é do backend, não do cliente.

### 3. Renomear o problema: não é "central de alertas", é "linha do tempo de episódios" — ⚠ CONFIRMAR

O produto não precisa de uma caixa de entrada. Ele precisa responder **uma** pergunta que hoje não
responde:

> "Eu não olhei o painel na semana passada. Aconteceu alguma coisa?"

Todas as superfícies atuais respondem "como está **agora**" (`DiagnosticsCard` = ciclo corrente;
`ProductionDiagnosticPanel` = pior dia do período, um único dia; `DeviceStatusSection` = um dia).
Nenhuma responde "o que aconteceu, e quando, e por quanto tempo".

A fronteira fica assim, e é a resposta ao item 4 do enunciado da T3:

| Superfície | Pergunta que responde | Eixo |
|---|---|---|
| `DiagnosticsCard` | O que está errado no ciclo atual | Estado |
| `ProductionDiagnosticPanel` | Qual o diagnóstico do período, e qual o pior dia | Estado + 1 dia |
| `DeviceStatusSection` | Qual inversor está com problema hoje | Estado |
| **Linha do tempo de episódios** (nova) | **Quando começou, quanto durou, já passou** | **Tempo** |

O nome importa: chamar de "Alertas" cria a expectativa de caixa de entrada (marcar como lido,
silenciar, notificar) que a Decisão 6 recusa. **Vocabulário fixado: "Episódios" / "Histórico de
ocorrências". Nunca "Alertas", "Notificações" ou "Central".**

### 4. O que se entrega: `daily[].diagnostics` no parser, agrupado em episódios

**Zero backend. Zero migration. Zero endpoint novo. Zero dependência nova.**

**4.1 — Contrato (extensão de parser, não payload novo).** `AnomalyDailyPoint`
(`frontend/src/lib/dashboard/contracts.ts:111-125`) ganha um campo, espelhando o que o backend já
manda (`src/mplacas/intelligence/router.py:174-186`):

```ts
interface AnomalyDiagnostic {
  code: string
  level: AnomalyLevel      // reusa ANOMALY_LEVELS (contracts.ts:108-109) — sem vocabulário novo
  message: string
  recommended_action: string
}
// em AnomalyDailyPoint:
diagnostics: AnomalyDiagnostic[]   // [] é legítimo: dia sem assessment (router.py:184-185)
```

Regras de parsing, herdadas do arquivo:
- Array ausente ou não-array → **`[]`**, não exceção. O campo é aditivo; um backend antigo (ou a
  T7 em voo) não pode quebrar a tela inteira. Difere de `daily`, que é estrutural e continua
  lançando (`contracts.ts:341`).
- Item malformado dentro do array → o item é descartado, o dia sobrevive. Nunca inventar `code`,
  `level`, `message` ou `recommended_action`.
- `level` fora de `ANOMALY_LEVELS` → item descartado (mesma disciplina de
  `optionalAnomalyLevel`, `contracts.ts:319-324`).

**Os 3 testes obrigatórios do §2.2** incidem sobre `parseAnomalyDaily`: payload válido com
`diagnostics`; payload **sem** o campo (deve dar `[]`, não erro); payload com item malformado
(deve descartar o item, não a resposta).

**4.2 — Agregação em episódios (apresentação, não cálculo).** A lista mostra **episódios**, não
dias. Um episódio é uma sequência de dias consecutivos com o **mesmo `code`**. Renderiza:

- data de início e de fim (ou "em curso" quando o episódio inclui o último dia da série);
- duração em dias;
- pior `level` do episódio (⚠ pelo `LEVEL_RANK` que **já existe** em
  `ProductionDiagnosticPanel.tsx:24-29` — extrair para módulo compartilhado, **nunca** duplicar);
- `message` e `recommended_action` do dia mais severo do episódio.

⚠ **Isto é agrupamento de itens já classificados, não classificação.** Nenhum limiar, nenhuma
divisão, nenhuma comparação numérica nova. O `level` de cada dia vem pronto do backend
(`intelligence/anomaly_engine.py:176-183`). Se em algum momento a implementação precisar de um
número que não veio no payload, **a Decisão 4 foi violada** e a tarefa deve parar.

**4.3 — Onde.** Módulo **Produção** (`frontend/src/pages/dashboard/ProductionPage.tsx`), abaixo de
`ProductionDiagnosticPanel` (`:254`), reusando o `anomalyState` que a página **já** carrega.
Nenhuma requisição nova em nenhum módulo. Não vai na Visão Geral: ela responde "minha conta está
ok" (ADR-072), e uma lista temporal ali competiria com o `DiagnosticsCard` pela mesma atenção.

**4.4 — Apresentação.** Severidade com **cor + texto + ícone**, tokens `--color-*-text` (plano
§2.3). Reusar `levelLabel`/`levelSeverity`/`SEVERITY_BG`/`SEVERITY_TEXT` de
`frontend/src/lib/dashboard/visuals.ts` — importados hoje por `ProductionDiagnosticPanel.tsx:5`.
Nenhum token novo, nenhuma classe crua de cor.

**4.5 — Indisponibilidade, com motivo explícito e distinto:**

| Situação | Detecção | O que a tela diz |
|---|---|---|
| Nenhum episódio no período | Nenhum dia com `level` diferente de NORMAL | "Nenhuma ocorrência nos últimos 90 dias." — afirmação positiva, nunca travessão nem lista vazia sem texto |
| Sem expectativa para o período | `expected_unavailable_reason` não nulo (`contracts.ts:141`) | Reusa `baselineUnavailableMessage` (`ProductionDiagnosticPanel.tsx:4,235`). **Nunca** "nenhuma ocorrência" — não saber é diferente de estar bem |
| 404 do endpoint | `anomalyState.error` igual a `NOT_FOUND` | Mesmo tratamento já existente (`ProductionDiagnosticPanel.tsx:213-223`) |
| Falha do endpoint | `anomalyState.error` igual a `SERVER_ERROR` | Estado de erro, nunca lista vazia |

A distinção entre a 1ª e a 2ª linha é a mesma armadilha da ADR-074, Decisão 3: transformar "não
sei" em "está tudo bem". **Uma lista vazia por ausência de baseline é a pior saída possível desta
tela** — ela afirma normalidade sem evidência.

### 5. Fadiga de alarme: o que **não** mostrar

Esta decisão é tão importante quanto o que se mostra, e é toda derivada de código verificado.

**5.1 — `PERFORMANCE_WITHIN_EXPECTED_RANGE` nunca aparece.** Todo dia NORMAL avaliado gera um
diagnóstico dizendo que está tudo bem (`src/mplacas/intelligence/anomaly_engine.py:194-202`). Numa
janela de 90 dias, uma usina saudável produz **90 diagnósticos**. Renderizá-los seria transformar
a feature no ruído que ela existe para evitar. **Filtro obrigatório: descartar todo item cujo
`level` seja NORMAL.**

**5.2 — Separar "problema da usina" de "lacuna do nosso dado".** O motor tem exatamente 6 códigos
(`anomaly_engine.py:134-241`), e só **um** significa que algo pode estar errado com a usina:

| Código | Nível | Natureza | Vai para a linha do tempo? |
|---|---|---|---|
| `PERFORMANCE_WITHIN_EXPECTED_RANGE` (`:197`) | NORMAL | Normalidade | **Não** (5.1) |
| `INCOMPLETE_INPUT_DATA` (`:136`) | ATTENTION | Nosso dado | **Não** — pertence ao frescor/confiança do dado |
| `EXPECTED_PRODUCTION_UNAVAILABLE` (`:153`) | ATTENTION | Nosso baseline | **Não** — já é dito por `expected_unavailable_reason` (4.5) |
| `LOW_PRODUCTION_WITH_LOW_IRRADIATION` (`:206`) | herda o dia | Clima explica | **Sim, rebaixado** — nunca como falha |
| `LOW_PRODUCTION_WITHOUT_CLIMATE_CONTEXT` (`:215`) | herda o dia | Sem contexto | **Sim**, com o texto de incerteza que o próprio código já traz |
| `LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION` (`:230`) | herda o dia | **Usina** | **Sim — é o item principal** |

`INCOMPLETE_INPUT_DATA` e `EXPECTED_PRODUCTION_UNAVAILABLE` são armadilhas concretas: ambos são
ATTENTION, ambos são por dia, e uma usina sem baseline pode gerá-los **todos os dias da janela** —
90 linhas idênticas culpando a usina por uma lacuna nossa. Eles são estado de confiança do dado,
não ocorrência.

**5.3 — Agrupar, sempre.** Sete dias consecutivos com o mesmo código são **um** episódio de sete
dias, nunca sete linhas (Decisão 4.2). Isto é exatamente o defeito que o canal de Telegram tem
hoje (Decisão 2, limitação 2) e que não deve ser reproduzido na tela.

**5.4 — Nada de contador global, badge ou sino.** Um número persistente ao lado de um ícone cria
pressão para "zerar", que exige "marcar como lido", que exige estado por usuário, que exige tabela
— exatamente a espiral que a Decisão 1 recusa. A `AttentionSummary`
(`AttentionSummary.tsx:11-31`) já cobre a necessidade de sinalização, e só para CRITICAL, por
decisão anterior deliberada (comentário em `:8-10`).

**5.5 — Teto de itens.** No máximo 10 episódios visíveis, do mais recente para o mais antigo, com
expansão explícita. Se uma usina tiver mais de 10 episódios em 90 dias, o problema não é a lista —
e a lista não deve fingir que é útil.

### 6. Ciclo de vida (reconhecer → resolver): confirmado fora de escopo, e recusado por ora

O plano manda "histórico primeiro, ciclo de vida numa segunda etapa". **Confirmado, com um
agravante:** a segunda etapa não é meramente adiada — ela é **impossível sem escolhas de produto
que ainda não foram feitas**, e este ADR recomenda não fazê-las agora.

"Reconhecer" e "resolver" são estado **por usuário** sobre um evento. Isso exige:

- tabela nova (com todo o custo da Decisão 9), **e**
- um `operational_user` como sujeito — mas os alertas de hoje não têm destinatário nomeado
  (Contexto: chat global, `cloud_jobs.py:477-480`), **e**
- decidir o que "resolvido" significa para um episódio que o motor determinístico continua
  recalculando a cada leitura: se o usuário marca "resolvido" e o dia seguinte volta a ser
  CRITICAL, é o mesmo episódio ou outro? Não há resposta óbvia, e uma resposta errada gera estado
  que discorda do motor — o pior desfecho possível.

Um episódio da Decisão 4 **se resolve sozinho**: ele ganha data de fim quando os dias voltam a
NORMAL. Isso entrega a maior parte do valor de "resolver" sem nenhuma das perguntas acima.

### 7. Retenção: nada novo a reter

Não há dado novo, logo não há política nova. Registra-se o que fica valendo, e por quê:

| Dado | Janela | Onde |
|---|---|---|
| Série diária de anomalia (fonte da linha do tempo) | Vive enquanto `daily_energy` viver — `RetentionService` **nunca** toca dado de produção, por regra explícita | `src/mplacas/retention/service.py:75-81` |
| Janela consultada pela UI | 90 dias, teto do endpoint | `src/mplacas/intelligence/router.py:322`; `frontend/src/lib/api.ts:72-74` |
| `outbox_events` (o que foi enviado) | 30 dias após DELIVERED/FAILED | `retention/service.py:121-132`; `core/config.py:80` |
| `alert_delivery_records` (dedupe) | 365 dias, conservador de propósito | `retention/service.py:52` e docstring `:39-46` |

Consequência: **a linha do tempo da Decisão 4 tem retenção melhor (90 dias, limitada só pelo teto
do endpoint) do que qualquer coisa construída sobre `outbox_events` (30 dias).** O caminho barato é
também o mais duradouro. Se um dia for preciso mais de 90 dias, o limite é o `le=90` de
`intelligence/router.py:322` — um parâmetro, não um schema.

### 8. Migration: nenhuma. E a convenção, registrada para quem vier depois

**Este ADR não produz migration.** A convenção fica registrada aqui para que a Decisão 9, se
acionada, não precise redescobri-la:

- Arquivo: `migrations/versions/YYYYMMDD_NNNN_slug.py`, com `NNNN` sequencial global de 4 dígitos.
- Dentro: `revision = "YYYYMMDD_NNNN"`, `down_revision = "<revision anterior>"`
  (`migrations/versions/20260802_0040_enable_postgresql_rls.py:11-12`) — **diverge do default do
  Alembic**, que é um hash aleatório.
- Última aplicada: `20260805_0043`
  (`migrations/versions/20260805_0043_add_organization_default_plant.py:3-4`).
  Próxima livre: **`0044`**. Reconfirme com `ls migrations/versions/` antes de criar.
- Docstring com `Revision ID:` / `Revises:` e a justificativa de domínio, incluindo o que acontece
  com as linhas existentes (o 0043 é a referência de qualidade).
- **Exige `reviewer` independente** (plano, regra 0.3.7).

### 9. Se e quando reabrir — gatilhos objetivos e o caminho pré-decidido — ⚠ CONFIRMAR

Esta decisão não é "nunca". É "não com o produto que existe hoje". Reabra quando **qualquer** um
destes for verdade — todos verificáveis, nenhum subjetivo:

1. **A entrega de alerta virar por organização.** Concretamente: `telegram_alert_chat_id` deixar de
   ser um `Settings` global (`core/config.py:57`) e o job deixar de iterar só
   `DEFAULT_ORGANIZATION_ID` (`cloud_jobs.py:497`). A partir daí existe "o alerta que **este**
   usuário recebeu", e um histórico in-app passa a ter um referente.
2. **`send_production_alert` ganhar um caller de produção**
   (`alerts/production_alert.py:392`, hoje só chamado por testes). Alerta por inversor é conteúdo
   que nenhuma tela cobre e que muda a conta de valor.
3. **Existir canal que o usuário possa perder** (e-mail, push, WhatsApp). Um histórico in-app é a
   rede de segurança de um canal assíncrono — sem canal, não há o que resgatar.
4. **Uso real medido da linha do tempo da Decisão 4.** Se ninguém expande episódios, uma central
   dedicada seria pior, não melhor.

**Caminho pré-decidido quando reabrir: (C) — ler `outbox_events`, não criar tabela.** Endpoint
`GET /alerts/history?plant_id=…` com `ReadPlant` + `set_principal_context`, filtrando
`event_type = "alert.delivery.requested"` (`alerts/outbox.py:21`), lendo `payload_json` via
`OutboxRepository` (que já valida o checksum, `events/outbox.py:57-66`). Deve **obrigatoriamente**
agrupar por incidente antes de serializar, sob pena de reproduzir a repetição de 7 dias da
Decisão 2. Retenção efetiva: 30 dias, ajustável por `retention_outbox_events_days`
(`core/config.py:80`) — **configuração, não migration**.

**⚠ CONFIRMAR — o custo real de uma tabela nova, caso (C) seja recusado no futuro.** Não é "uma
migration". Adicionar uma tabela ao projeto exige, hoje, mexer em testes que fixam o inventário
inteiro:

1. Migration criando a tabela (`0044` ou posterior).
2. **Segunda migration** criando a policy RLS e o `ENABLE`/`FORCE ROW LEVEL SECURITY` — a migration
   `20260802_0040` já foi aplicada; editá-la **não** cria policy retroativamente.
3. `src/mplacas/db/rls_inventory.py:21-46` — entrada nova.
4. `tests/test_rls_inventory.py:26-27` — `len(RLS_TABLES) == 24` vira 25, e o import do
   `db_models` novo entra na lista de `:6-22`.
5. `tests/test_postgres_application_rls.py:207` — o `== 24` vira 25.
6. `tests/test_rls_migration_contract.py:31-32` — **este é o problema real**: ele afirma
   `set(migration.ALL_TABLES) == set(RLS_TABLES)` sobre a migration `20260802_0040`, **já
   aplicada**. Adicionar uma tabela ao inventário quebra esse teste a menos que se edite
   `ALL_TABLES` dentro de uma migration histórica — o que faria o teste passar sem que a policy
   exista em nenhum banco já migrado. **Fazer isso seria trocar um teste verde por um furo de
   isolamento multi-tenant.** O contrato precisa ser reestruturado (unir a cobertura de RLS ao
   longo das migrations) **antes**, como tarefa própria, com `reviewer`.
7. Janela de retenção nova em `RetentionWindows` (`retention/service.py:39-70`) mais o setting
   correspondente (`core/config.py:80` é o padrão a seguir).

Sete pontos, um deles tocando o mecanismo de isolamento entre organizações. **Isso é o custo que a
Decisão 1 evita**, e é a razão de (C) ser o caminho pré-decidido, não (A).

### 10. Efeito sobre os critérios de aceite da T3

| Critério original (plano §3, T3) | Estado sob este ADR |
|---|---|
| ADR de decisão (persistir × recalcular) escrito e aprovado | **Este documento.** Resposta: nenhum dos dois — já está persistido, e não é o que falta |
| Se houve migration: convenção respeitada e testada | **N/A** — não há migration (Decisão 8) |
| Endpoint de leitura com `ReadPlant` + `set_principal_context` | **N/A** — nenhum endpoint novo (Decisão 4). O endpoint já consumido cumpre ambos (`intelligence/router.py:319-325`) |
| Severidade com cor + texto + ícone | **Mantido** (Decisão 4.4) |
| Gate §0.4 verde | **Mantido**, só no lado frontend |
| Revisado por `reviewer` (toca schema/migration) | **Rebaixado**: sem schema e sem migration, a revisão obrigatória cai. Recomendado ainda assim para a regra 5.2 (o que não mostrar), que é decisão de produto com risco de confiança |

## Consequências

### Positivas

- **O produto passa a responder "aconteceu algo enquanto eu não olhava?"** — a única pergunta que
  nenhuma das cinco superfícies atuais responde — sem uma linha de backend.
- **Nenhuma migration, nenhum schema, nenhum endpoint, nenhuma dependência.** A tarefa mais cara do
  plano (§2.6) passa a ser uma das mais baratas.
- **Nenhum estado duplicado.** O motor determinístico continua sendo a única fonte de severidade;
  a tela agrupa o que ele já disse, e não pode divergir dele por construção.
- **Retenção de 90 dias em vez de 30**, sem esforço (Decisão 7).
- **A quinta taxonomia de severidade não nasce.** O produto reusa `AnomalyLevel` e os tokens
  existentes.
- Fica documentado, com `arquivo:linha`, que **o conteúdo do alerta já é persistido** — corrigindo
  a afirmação do plano que teria custado uma migration desnecessária.
- Fica documentado que **`send_production_alert` não tem caller de produção**, um fato que a
  ADR-074 (Decisão 8, linha "Alerta específico daquele inversor") assumiu implicitamente como
  existente.

### Negativas

- **Um item do plano é recusado, não entregue.** Se a expectativa (do usuário ou de um stakeholder)
  era uma central de alertas visível, este ADR não a satisfaz. Por isso a Decisão 1 é
  ⚠ CONFIRMAR.
- **A linha do tempo cobre só a fonte de anomalia diária.** O alerta executivo (nível de ciclo) não
  entra; seu histórico existe parcialmente em `/reports/monthly/history`, já consumido
  (`frontend/src/lib/api.ts:98`, plano §1.3), mas sem os diagnósticos. Lacuna assumida.
- **Não há histórico do que foi *enviado*.** Se um dia alguém perguntar "que mensagem exatamente o
  sistema mandou no dia 3?", a resposta continua sendo consultar `outbox_events` por fora do
  produto — e só nos últimos 30 dias.
- **Uma superfície a mais na página de Produção**, que já é o módulo mais denso (12,07 kB gzip,
  plano §1.4). O agrupamento em episódios (Decisão 4.2) é o que impede que ela vire uma lista
  longa, mas é densidade adicional.
- **A dívida da taxonomia concorrente não é paga aqui.** `production-alerts.ts:10-13,188-247`
  continua calculando severidade no cliente com limiares próprios, ao lado da nova linha do tempo.
  Este ADR não amplia a dívida, mas conviverá com ela até a T7 ou uma tarefa sucessora tratá-la.
- **Se a Decisão 1 for revertida no futuro**, parte do trabalho da Decisão 4 (o agrupamento em
  episódios) precisará migrar para o backend — retrabalho previsto, e barato.

## Validação

**Contrato (`parseAnomalyDaily`) — os 3 casos obrigatórios do §2.2:**

- Payload válido com `diagnostics` populado → array parseado, com `code`, `level`, `message` e
  `recommended_action` preservados sem transformação.
- Payload **sem** o campo `diagnostics` → array vazio, **sem lançar**. Teste que falharia se alguém
  trocasse a leitura tolerante por uma exigência estrutural — é o que impede a T7 (ou qualquer
  mudança aditiva do backend) de derrubar a tela.
- Item malformado no array (`level` inválido, `message` ausente, item não-objeto) → item descartado,
  demais itens e o dia preservados. Nunca inventar campo.

**Comportamento — os testes que provam as decisões:**

- Série com 90 dias NORMAL → **nenhum episódio** e a frase afirmativa "Nenhuma ocorrência…".
  Este é o teste da Decisão 5.1: se alguém remover o filtro de NORMAL, ele falha com 90 itens.
- Série com `expected_unavailable_reason` preenchido → mensagem de baseline indisponível, e
  **jamais** "Nenhuma ocorrência". Teste da armadilha "não sei é diferente de está bem" (4.5).
- Sete dias consecutivos com o mesmo `code` → **um** episódio de 7 dias, com início, fim e duração.
  Teste da Decisão 5.3 — falha se alguém renderizar por dia.
- Dois blocos separados por um dia NORMAL → **dois** episódios, não um.
- Episódio que inclui o último dia da série → rotulado "em curso", nunca com data de fim futura.
- Série contendo apenas `INCOMPLETE_INPUT_DATA` / `EXPECTED_PRODUCTION_UNAVAILABLE` → **nenhum
  episódio** na linha do tempo. Teste da Decisão 5.2 — é o que impede culpar a usina por lacuna
  nossa.
- Severidade sempre com texto acessível além da cor; nenhuma classe crua de cor (o teste de tokens
  do projeto já cobre, plano §2.3).
- Erro (`SERVER_ERROR`) e 404 (`NOT_FOUND`) produzem estados distintos entre si e distintos de
  "nenhuma ocorrência".
- **Guarda estática contra cálculo no cliente**, no padrão já existente do projeto
  (`frontend/src/lib/dashboard/no-client-computed-expected-production.test.ts` e o equivalente
  criado na T1d): o módulo de episódios não pode conter divisão, multiplicação, limiar numérico nem
  comparação contra constante de severidade. Só agrupamento e formatação.
- `LEVEL_RANK` existe **uma** vez no projeto após a mudança (hoje em
  `ProductionDiagnosticPanel.tsx:24-29`). Teste ou verificação de que não há segunda cópia.

**Gate:**

- Frontend §0.4 verde, sem regressão contra o baseline vigente; delta do chunk `ProductionPage`
  registrado.
- **Backend não é tocado** — nenhum arquivo `.py` alterado. Se o diff final contiver um `.py`, a
  Decisão 4 foi violada.

## Reversibilidade

**Altíssima para a Decisão 4.** Um campo de parser e um componente. Remover é deletar dois arquivos
e três linhas; nada é persistido, nada muda de contrato de rede, nenhum outro consumidor depende.
O `diagnostics` já vinha no payload e já era descartado — voltar ao estado atual é literalmente
voltar a descartá-lo.

**Alta para a Decisão 1 (a recusa).** Não construir não fecha porta nenhuma: os dados continuam
sendo produzidos e persistidos (`outbox_events`) exatamente como hoje, sem nenhuma perda enquanto a
decisão estiver de pé — respeitada a janela de 30 dias, que já é o comportamento atual. A Decisão 9
descreve o caminho de volta com gatilhos objetivos.

**Média-baixa para a percepção de produto.** Vale aqui a mesma advertência da ADR-074, Decisão 8:
depois que uma superfície existe, retirá-la é regressão percebida. Por isso a Decisão 3 fixa o
vocabulário "Episódios" e a Decisão 5.4 proíbe sino/badge — para que a linha do tempo **não** crie
a expectativa de caixa de entrada que depois não se poderia recuar.

**Baixa para a Decisão 9, item 6 (contrato de RLS).** Se algum dia uma tabela nova for criada, a
reestruturação de `tests/test_rls_migration_contract.py` é irreversível na prática — ninguém volta
um contrato de segurança para uma forma mais frouxa. Mais um motivo para não criar tabela sem
necessidade demonstrada.

## Riscos e o que fica fora de escopo

**Riscos:**

- *A recusa ser lida como "o produto não precisa de alertas".* Não é. É "o produto precisa do eixo
  do tempo, e ele custa quase nada; a caixa de entrada custa muito e entrega pouco **hoje**". Se o
  gatilho 1 da Decisão 9 (entrega por organização) for acionado, a conta inverte.
- *`expected_unavailable_reason` dominante.* Uma usina sem baseline sazonal nunca produz `level`
  algum (`intelligence/anomaly_service.py:246-258` devolve `assessment=None`), então a linha do
  tempo fica permanentemente no estado 2 da tabela 4.5. É estado honesto, mas é uma tela vazia com
  explicação. Risco simétrico ao `INSUFFICIENT_DEVICE_HISTORY` da ADR-074 — e a mitigação é a
  mesma: olhar a resposta real da usina de produção antes de investir em refinamento visual.
- *Discordância percebida com o chip "Critério de alerta".* O chip usa limiares próprios do cliente
  (`production-alerts.ts:10-13`) e a linha do tempo usa `AnomalyLevel` do backend. Eles **vão**
  discordar em casos de fronteira, na mesma tela (`ProductionDiagnosticPanel.tsx:415-425` fica
  logo acima). Não há mitigação técnica dentro deste escopo — a solução é a T7 ou sucessora
  eliminar o motor do cliente. **Sinalizar ao `product-uiux-lead` antes de implementar** se as
  duas ficarão visíveis simultaneamente.
- *Reintrodução de cálculo no cliente durante a implementação.* O agrupamento em episódios é
  vizinho perigoso de "calcular duração ponderada", "somar perda do episódio", "ranquear
  episódios". A guarda estática da Validação existe para isso.
- *A T7 alterar `parseAnomalyDaily` em paralelo.* O diff da T7 na working tree já adiciona campos ao
  mesmo objeto do payload diário (`intelligence/router.py`, versão modificada). Conflito de merge
  provável, semanticamente trivial — mas exige que a T3 seja implementada **depois** da T7 fechar.

**Fora de escopo, explicitamente:**

- Qualquer rota, aba, sino, badge, drawer ou página "Alertas" (Decisão 1).
- Qualquer tabela, modelo ou migration (Decisões 2, 8, 9).
- Qualquer endpoint novo, inclusive `GET /alerts/history` (Decisão 9 — pré-decidido, não
  autorizado).
- Reconhecer / resolver / silenciar / marcar como lido (Decisão 6).
- Notificação por e-mail, push, toast in-app ou WhatsApp — canal novo é decisão própria, e é o
  gatilho 3 da Decisão 9.
- Preferências de alerta por usuário (limiar, horário, canal).
- Alerta por inversor — depende de `send_production_alert` ganhar caller de produção (Decisão 9,
  gatilho 2); a ADR-074, Decisão 8 já o listava como fora de escopo.
- Histórico de alerta executivo (nível de ciclo).
- Corrigir a taxonomia concorrente de `production-alerts.ts` — dívida preexistente, endereçada pela
  T7 ou sucessora, **não ampliada aqui**.
- Alterar `RetentionWindows`, `retention_outbox_events_days` ou qualquer política de retenção
  (Decisão 7).
- Alterar `alerts/`, `events/`, `intelligence/` ou qualquer arquivo `.py` (Decisão 4).
