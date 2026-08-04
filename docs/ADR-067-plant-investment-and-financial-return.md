# ADR-067 — Investimento da usina, ROI e projeção de payback

## Status

Aceito — 2026-08-04.

Os quatro pontos abaixo foram revisados e aprovados como refinamentos técnicos
consistentes com a decisão (D)/(F) já tomada pelo usuário: (1) ROI nasce com cobertura
baixa e cresce um ciclo por mês — consequência aceita, não motivo para reverter (F); (2)
separação de `unavailable_reason` em dois campos; (3) cadastro do CAPEX via diálogo na
própria seção de ROI; (4) valor investido gravado em `details` do audit event.

## Contexto

O gap analysis contra concorrentes do setor solar apontou o retorno financeiro do
investimento (ROI e payback) como a lacuna de maior valor percebido pelo dono da usina —
e também a de maior esforço. O Mplacas já sabe quanto o cliente economiza por ciclo, mas
não sabe quanto ele investiu, e portanto não consegue responder à pergunta que ele mais
faz: "quando isso se paga?".

Estado atual verificado no código:

- **Não existe nenhum campo de investimento ou CAPEX no schema.** Confirmado em
  `src/mplacas/db/models.py` (`Plant`), `src/mplacas/organizations/db_models.py`,
  `src/mplacas/billing/db_models.py` e `src/mplacas/photovoltaic/db_models.py`.
- **`Plant.commissioned_on` já existe** (`Date`, nullable — ADR-057, migration
  `20260802_0032_add_plant_technical_configuration.py`). É a data de referência da usina
  e NÃO deve ser recriada.
- **`plants` já está sob RLS** (`migrations/versions/20260802_0040_enable_postgresql_rls.py`,
  entrada `"plants": "organization_id"` em `ORGANIZATION_TABLES`). A policy é por linha,
  não por coluna.
- **`monthly_report_snapshots`** (`src/mplacas/reports/db_models.py`, ADR-038) é imutável,
  versionado por `calculation_version`, com `UniqueConstraint` em `bill_id`, e é
  materializado no ato da confirmação da fatura (`src/mplacas/billing/router.py`, linha
  127, dentro de `POST /billing/{bill_id}/confirm`).

### Achado que muda o desenho: a economia NÃO está no snapshot

A decisão do usuário (F) é que a economia acumulada venha dos snapshots imutáveis, e não
de recomputação sobre `utility_bills` — o que está arquiteturalmente correto, porque
recomputar faria o ROI mudar retroativamente sempre que o motor de cálculo evoluísse.

Porém, a inspeção de `src/mplacas/reports/report_projection.py` mostra que
**`estimated_savings_brl` não é projetado como `ReportMetric`**. As métricas financeiras
do relatório param em `bill_energy_component_brl`; a economia estimada existe apenas em
`EnergyCycleIntelligence` e no contrato de API do dashboard, nunca no `payload_json` do
snapshot.

Consequência direta: **hoje é impossível somar economia a partir dos snapshots.** A
decisão (F) exige, como pré-requisito, acrescentar a economia ao relatório mensal — o que
altera o `payload_json` e, por ADR-038, vale apenas para snapshots emitidos daí em diante.
Snapshots já gravados permanecerão sem a métrica, para sempre, por definição de
imutabilidade.

Isso não invalida a decisão (F). Ao contrário: é exatamente por isso que a decisão do
usuário de expor cobertura explícita (`cycles_counted` versus `cycles_expected`) deixa de
ser um refinamento e passa a ser condição de correção do endpoint. Sem cobertura
explícita, o ROI mentiria por omissão desde o primeiro dia.

## Decisão

### 1. Pré-requisito: persistir a economia no relatório mensal

`src/mplacas/reports/report_projection.py` passa a projetar duas métricas novas em
`_project_metrics`, imediatamente após `bill_energy_component_brl`:

- `estimated_savings_brl`, rótulo "Economia estimada", `unit="BRL"`,
  `nature="CALCULATED"`, `source=ENGINE_SOURCE`;
- `savings_unavailable_reason`, rótulo "Motivo de indisponibilidade da economia",
  `unit=None`, `nature="UNAVAILABILITY_REASON"`, `source=ENGINE_SOURCE`.

Quando a economia é `None`, `estimated_savings_brl` NÃO é omitida: ela é emitida com
`value` vazio e o motivo preenchido na segunda métrica. Omitir a chave tornaria
indistinguíveis "snapshot antigo, sem o conceito" e "snapshot novo, com economia
indisponível" — e essa distinção é justamente o que o cálculo de cobertura precisa fazer.

`calculation_version` do snapshot é `mplacas.__version__` (ver `report_projection.py`,
linha 269), logo a mudança já fica registrada no versionamento existente sem mecanismo
novo. Nenhum snapshot existente é reescrito: ADR-038 permanece intacto.

### 2. Migration Alembic

Arquivo `migrations/versions/20260804_0042_add_plant_investment_amount.py`, conforme a
skill `alembic-migrations`:

- `revision = "20260804_0042"`, `down_revision = "20260803_0041"` (a última migration
  aplicada é `20260803_0041_allow_legacy_tenant_uuids.py`; o worker DEVE reconferir a
  pasta antes de gerar, porque a sequência é contínua entre datas).
- `plants.investment_amount_brl` — `Numeric(12, 2)`, `nullable=True`.
- `plants.investment_recorded_on` — `Date`, `nullable=True`.
- `CheckConstraint("investment_amount_brl IS NULL OR investment_amount_brl > 0",
  name="ck_plants_investment_amount_positive")`, seguindo exatamente a nomenclatura das
  constraints já existentes em `Plant.__table_args__`
  (`ck_plants_installed_power_positive`, `ck_plants_ac_capacity_positive`).
- Ambas as colunas nullable desde o início: não há backfill, não há passo de `NOT NULL`.
  A regra de três migrations da skill não se aplica aqui.
- `op.batch_alter_table` para a criação da CHECK, porque o projeto roda SQLite em
  desenvolvimento e SQLite não aceita adicionar constraint fora de batch mode.
- `downgrade()` remove constraint e colunas, na ordem inversa.

`Numeric(12, 2)` comporta até R$ 9.999.999.999,99 — folgado para usinas de geração
distribuída e consistente com a precisão monetária já usada em `utility_bills`.

### 3. RLS: a coluna nova herda a policy existente, e isso é suficiente

`plants` já consta em `ORGANIZATION_TABLES` na migration `20260802_0040`, com policy
`mplacas_rls_isolation` sobre `organization_id`. As policies do PostgreSQL são avaliadas
**por linha**, não por coluna: qualquer coluna nova de `plants` fica automaticamente sob a
mesma policy, sem policy adicional e sem alteração na migration de RLS.

Fica registrado explicitamente porque `investment_amount_brl` é o primeiro dado
declaradamente financeiro-sensível a viver em `plants`, e a pergunta "precisa de policy
nova?" vai reaparecer. A resposta é não — mas a ausência de policy nova NÃO dispensa
teste de fronteira entre tenants: o risco real não está no RLS do Postgres, está em um
endpoint que resolva `plant_id` sem passar pelo `PlantScope` do chamador. É isso que a
suíte de fronteira testa, e é por isso que ela é obrigatória nesta frente.

### 4. Endpoint de configuração financeira

Separado da configuração técnica (ADR-057), em `src/mplacas/plants/router.py`, seguindo
literalmente o padrão de `technical-configuration`:

```
GET   /plants/{plant_id}/financial-configuration   -> ReadPlantPath
PATCH /plants/{plant_id}/financial-configuration   -> AdminPlantPath
```

- Dependências de `mplacas.core.tenancy`: `ReadPlantPath` para leitura, `AdminPlantPath`
  para escrita. Ambas retornam **404, não 403**, para usina de outra organização — a
  convenção já documentada no docstring de `update_plant_location`.
- `set_principal_context(session, scoped.principal)` antes de qualquer query, como em
  todo o router.
- Request model `PlantFinancialConfigurationUpdateRequest` com
  `model_config = ConfigDict(extra="forbid")`, campos
  `investment_amount_brl: Decimal | None = Field(default=None, gt=0, max_digits=12,
  decimal_places=2)` e `investment_recorded_on: date | None = None`, com o mesmo
  validador de "pelo menos um campo" já usado em
  `PlantTechnicalConfigurationUpdateRequest`. Semântica de `PATCH` por
  `model_fields_set`, permitindo apagar um campo enviando `null` explicitamente.
- Validação de negócio: se `investment_recorded_on` e `commissioned_on` estiverem ambos
  preenchidos, exigir `investment_recorded_on <= commissioned_on + 1 ano`? **Não.** Não há
  regra de negócio confiável aqui e uma validação inventada só cria atrito. A data é
  informativa; a data de referência do cálculo é `commissioned_on`.
- Auditoria obrigatória via `AuditEventRepository(session).record(...)`, com
  `action="plant.financial_configuration_updated"`, `resource_type="plant"`,
  `resource_id=str(plant.id)`, `outcome="SUCCEEDED"` e
  `details=payload.model_dump(mode="json", exclude_unset=True)` — exatamente o formato de
  `plant.technical_configuration_updated`, inclusive gravando o valor investido em
  `details`. Gravar o valor é intencional: é dado financeiro cuja alteração precisa ser
  rastreável, e `audit_events` já está sob RLS por `organization_id` (ADR-039/ADR-056-RLS).
- `PATCH` só grava se a usina existir no escopo; commit único ao final, com o audit event
  na mesma transação, como no restante do router.

### 5. Endpoint de leitura do retorno financeiro

`GET /energy/financial-return/latest?plant_id=` em
`src/mplacas/intelligence/router.py`, com a dependência `ReadPlant` (a variante que
resolve `plant_id` por query string, já usada por `/energy/executive/latest` e
`/energy/trends/latest`), servido por um serviço novo
`src/mplacas/intelligence/financial_return_service.py`.

Contrato de resposta:

```json
{
  "plant_id": "...",
  "investment_amount_brl": "48000.00",
  "investment_recorded_on": "2024-03-11",
  "commissioned_on": "2024-03-01",
  "accumulated_savings_brl": "9120.55",
  "average_monthly_savings_brl": "760.05",
  "cycles_counted": 12,
  "cycles_expected": 17,
  "roi_percent": "19.0",
  "payback_projection_months": 63,
  "unavailable_reason": null,
  "payback_unavailable_reason": null
}
```

Definições, sem ambiguidade:

- `accumulated_savings_brl`: soma da métrica `estimated_savings_brl` dos snapshots de
  `monthly_report_snapshots` da usina cujo valor está preenchido. Snapshots sem a métrica
  (emitidos antes da Etapa A) e snapshots com a métrica vazia **não somam e não contam**.
  Nunca há recomputação sobre `utility_bills`.
- `cycles_counted`: número de snapshots que contribuíram para a soma acima.
- `cycles_expected`: número de meses de referência entre `commissioned_on` e o mês de
  referência do snapshot mais recente da usina, inclusive nas duas pontas. Se
  `commissioned_on` for nulo, `cycles_expected` é `null` e a interface não exibe
  cobertura — mas o ROI continua sendo calculado sobre o que existe.
- `average_monthly_savings_brl` = `accumulated_savings_brl / cycles_counted`, 2 casas,
  `ROUND_HALF_UP`. Campo acrescentado ao contrato pedido pelo usuário porque é o
  denominador da projeção; sem ele a projeção é uma caixa-preta que o cliente não
  consegue conferir.
- `roi_percent` = `accumulated_savings_brl / investment_amount_brl * 100`, 1 casa,
  `ROUND_HALF_UP`. É retorno **realizado até aqui**, jamais extrapolado, jamais anualizado.
- `payback_projection_months` = `cycles_counted + ceil((investment_amount_brl -
  accumulated_savings_brl) / average_monthly_savings_brl)`. Quando a economia acumulada
  já cobre o investimento, o valor é `cycles_counted` (o payback já ocorreu) e a interface
  troca o texto de projeção por "investimento já recuperado".

Regras de indisponibilidade, com dois campos e um único enum
(`FinancialReturnUnavailableReason`):

- `unavailable_reason = INVESTMENT_NOT_REGISTERED` quando `investment_amount_brl` é nulo.
  Todos os campos derivados vêm `null`.
- `unavailable_reason = NO_CONSOLIDATED_SAVINGS` quando `cycles_counted == 0`.
  `accumulated_savings_brl`, `roi_percent` e o payback vêm `null` — **nunca R$ 0,00**,
  mesmo princípio de `savings_unavailable_reason` no motor de energia.
- `payback_unavailable_reason = INSUFFICIENT_HISTORY` quando `cycles_counted < 6`, ou
  quando `average_monthly_savings_brl <= 0`. Nesse caso `roi_percent` continua preenchido
  e apenas `payback_projection_months` vem `null`.

A separação em dois campos é um refinamento deliberado sobre o pedido original de um
campo único: com um só campo, um cliente não conseguiria distinguir "não há ROI" de "há
ROI mas não há payback", e acabaria escondendo o ROI válido de uma usina com 3 ciclos. O
enum permanece único, com os três valores especificados.

### 6. O que este endpoint NÃO faz

Não materializa snapshots. É estritamente leitura. Materializar em um `GET` faria uma
requisição de leitura gravar dado imutável, com o agravante de que o snapshot
retroativo seria calculado com o motor de hoje, e não com o motor da época do ciclo —
contrariando o espírito do ADR-038. A consequência aceita é que faturas confirmadas antes
da Etapa A ficam fora da cobertura permanentemente, e é isso que `cycles_expected` torna
visível ao usuário em vez de esconder.

### 7. Frontend

- Seção nova de retorno financeiro na `DashboardPage`, no padrão de seção já existente
  (`EnergyProductionSection`, `TechnicalPerformanceSection`).
- Barra de progresso do acumulado em direção ao CAPEX. Cor de preenchimento: `brand-primary`
  (é progresso, não é estado de saúde) — NUNCA `success`, para não sugerir "está tudo bem".
  Percentual sempre com rótulo textual ao lado, nunca só a barra.
- Rótulo de cobertura sempre visível quando `cycles_counted < cycles_expected`, com texto
  explícito do tipo "baseado em 12 de 17 ciclos com relatório consolidado". Esse rótulo é
  parte do contrato de honestidade do indicador, não um detalhe de UI: sem ele o número
  engana.
- `payback_projection_months` sempre rotulado como PROJEÇÃO, com a premissa visível
  ("mantida a média de economia dos últimos ciclos"). Nunca renderizar como data.
- Estados indisponíveis com mensagem específica por motivo, no padrão de
  `savingsUnavailableMessage` em `frontend/src/lib/dashboard/contracts.ts`.
- Cadastro do valor investido: **não criar uma área de configurações nova.** O frontend
  hoje tem apenas `DashboardPage` e `LoginPage`; introduzir um shell de configurações é
  uma decisão de produto maior do que esta frente. A entrada é um diálogo acionado a
  partir do próprio estado `INVESTMENT_NOT_REGISTERED` da seção de ROI — o usuário
  encontra o campo exatamente onde sente a falta dele. O diálogo só aparece para perfil
  ADMIN; para READ, a seção mostra a mensagem sem ação. Um shell de configurações fica
  como decisão separada, quando houver uma segunda coisa a configurar.

### 8. Roteamento de agentes: reviewer obrigatório

Esta frente toca migrations, `plants` sob RLS (organizations), audit trail e o pipeline de
relatório que serve billing. Pelo `CLAUDE.md`, **toda etapa que mexa em schema, endpoint
ou snapshot passa pelo reviewer antes de ser dada por concluída** — Etapas A, B, C e D. A
Etapa E (frontend) não exige reviewer.

## Consequências

### Positivas

- Responde à pergunta de maior valor para o dono da usina, com número rastreável até uma
  fonte imutável e versionada (ADR-038), e não a uma recomputação que mudaria a cada
  release do motor.
- A cobertura explícita (`cycles_counted` versus `cycles_expected`) transforma a maior
  fraqueza da abordagem em recurso de credibilidade: o Mplacas mostra em cima de quantos
  ciclos o ROI foi calculado. Nenhum concorrente pesquisado faz isso.
- O CAPEX passa a existir no modelo de dados, abrindo caminho para indicadores derivados
  (R$ por kWp instalado, comparação entre usinas de uma mesma organização) sem migration
  adicional.
- Isolamento entre tenants sem custo extra de policy: a coluna nasce sob a RLS já ativa.

### Negativas

- **O ROI começa com histórico curto e não tem como recuperar o passado.** Faturas
  confirmadas antes da Etapa A não têm economia no snapshot, e por imutabilidade nunca
  terão. Uma usina com 3 anos de histórico pode exibir ROI baseado em 2 ciclos no primeiro
  mês após o deploy. É a consequência direta e aceita da decisão (F); a alternativa —
  recomputar sobre `utility_bills` — foi rejeitada por produzir um número que muda sozinho
  a cada atualização do motor de cálculo, o que é pior.
- **A projeção de payback é linear e ingênua.** Assume economia mensal constante, o que
  ignora sazonalidade da geração, degradação dos módulos (já modelada em ADR-060) e
  reajuste tarifário anual — todos com efeito material em um horizonte de 5 a 7 anos. O
  piso de 6 ciclos reduz o ruído mas não corrige o viés. Aceito porque uma projeção
  rotulada como projeção, com premissa visível, é honesta; um modelo financeiro elaborado
  seria mais preciso e muito mais difícil de explicar ao cliente. Um modelo que incorpore
  sazonalidade e degradação é o ADR seguinte, não este.
- **O valor investido é digitado pelo usuário, sem validação possível.** Um CAPEX errado
  produz um ROI errado com aparência de rigor. Mitigação parcial: CHECK de positividade,
  audit trail de toda alteração e data de registro visível na interface.
- **A economia entra no `payload_json` do snapshot, ampliando o contrato imutável.** Toda
  ampliação de contrato imutável é irreversível na prática — as duas métricas novas passam
  a existir para sempre nos snapshots emitidos daqui em diante. O desserializador em
  `src/mplacas/reports/snapshot.py` já lê métricas por lista genérica
  (`ReportMetric(**item)`), então snapshots antigos continuam desserializando sem erro;
  mas qualquer consumidor que assuma um conjunto fixo de métricas precisa ser revisto.
- Esforço concentrado: cinco etapas, quatro delas com reviewer obrigatório. É a frente
  mais cara aprovada até aqui, e foi aprovada com essa consciência (decisão D).

## Validação

- Migration: `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head`, em
  SQLite e Postgres, mais o teste de contrato de migration no padrão de
  `tests/test_database_migration_contracts.py`. Teste explícito de que a CHECK rejeita
  valor zero e negativo, e aceita `NULL`.
- Fronteira entre tenants para os dois endpoints novos, no rigor de
  `tests/test_photovoltaic_tenant_boundaries.py`: `plant_id` de outra organização retorna
  404 (não 403 e nunca 200), tanto em `GET` quanto em `PATCH`, tanto na configuração
  financeira quanto no retorno financeiro; e credencial READ recebe 403 no `PATCH`.
- Auditoria: teste de que `PATCH /plants/{id}/financial-configuration` grava
  `plant.financial_configuration_updated` com `organization_id` correto, no padrão de
  `tests/test_audit_repository.py`.
- Retorno financeiro: um teste por motivo de indisponibilidade
  (`INVESTMENT_NOT_REGISTERED`, `NO_CONSOLIDATED_SAVINGS`, `INSUFFICIENT_HISTORY`), mais o
  caso de cobertura parcial (`cycles_counted` menor que `cycles_expected`, com snapshots
  antigos sem a métrica no meio da série), mais o caso de payback já atingido, mais um
  teste de que nenhum campo indisponível vem como `0` ou `"0.00"`.
- Snapshot: teste de que um snapshot gravado antes da Etapa A continua desserializando e é
  contado como não coberto, e de que nenhum snapshot existente teve `payload_sha256`
  alterado.

## Reversibilidade

Média. Os dois endpoints e o frontend são removíveis sem sequelas. A migration é
reversível pelo `downgrade()`, com perda do CAPEX cadastrado — aceitável, é um único
número por usina, recadastrável.

O ponto irreversível é a ampliação do `payload_json` do snapshot (Etapa A): snapshots
emitidos com as métricas novas as terão para sempre. Reverter significaria parar de
emitir as métricas dali em diante, deixando uma janela no meio da série — nunca apagar o
que já foi gravado. Se a decisão (F) for revista no futuro em favor de uma tabela de
consolidação financeira dedicada, o ponto de extensão é o `financial_return_service.py`,
única peça que conhece a origem da economia acumulada; nem os endpoints nem o frontend
precisariam mudar.

## Pontos que exigem confirmação antes de virar Aceito

1. **BLOQUEANTE — a economia não está no snapshot hoje.** A decisão (F) só é implementável
   depois da Etapa A, e o ROI nasce com cobertura baixa, crescendo um ciclo por mês. Isso
   precisa estar claro antes de qualquer linha de código: o entregável do primeiro mês é
   um indicador honesto com pouco histórico, não um ROI completo do passado da usina. Se a
   expectativa for ROI histórico completo desde o comissionamento, a decisão (F) precisa
   ser revista — e a alternativa (recomputar sobre `utility_bills`) tem o defeito já
   descrito em "Negativas".
2. **Separação de `unavailable_reason` em dois campos** (ver Decisão, item 5). É um
   refinamento sobre o contrato pedido; com um campo único, o frontend deixa de conseguir
   mostrar ROI sem payback.
3. **Cadastro do CAPEX por diálogo na própria seção de ROI, sem área de configurações**
   (ver Decisão, item 7). É decisão de produto, não só de implementação.
4. **Gravar o valor investido em `details` do audit event.** É dado financeiro do cliente
   em uma tabela de auditoria com retenção própria (ADR-048). O padrão do projeto já grava
   o payload completo em `plant.technical_configuration_updated`, e a tabela está sob RLS;
   ainda assim, é o primeiro valor monetário do cliente a entrar em `audit_events`.

## Plano de implementação

Cinco etapas. As Etapas A a D exigem reviewer antes de serem fechadas (Decisão, item 8).

**Etapa A — economia no relatório mensal.** Não depende de nada; é pré-requisito de tudo.
Projetar `estimated_savings_brl` e `savings_unavailable_reason` como `ReportMetric` em
`src/mplacas/reports/report_projection.py`. Testes: métrica presente com valor, métrica
presente com valor vazio mais motivo, snapshot antigo continua desserializando,
`payload_sha256` de snapshots existentes inalterado. Reviewer obrigatório — toca o
pipeline de relatório imutável que serve billing.

**Etapa B — migration do CAPEX.** Independente de A; pode ir em paralelo. Modelo `Plant`
mais migration `20260804_0042` conforme a Decisão, item 2, seguindo a skill
`alembic-migrations`: conferir o maior número na pasta antes de gerar, ler o diff
autogerado antes de aplicar, `batch_alter_table` para a CHECK, `downgrade()` simétrico,
ciclo upgrade / downgrade -1 / upgrade, teste de contrato de migration. Reviewer
obrigatório.

**Etapa C — endpoint de configuração financeira.** Depende de B. `GET` e
`PATCH /plants/{plant_id}/financial-configuration` em `src/mplacas/plants/router.py`, com
`ReadPlantPath` e `AdminPlantPath`, audit event `plant.financial_configuration_updated`, e
a suíte de fronteira entre tenants no rigor de
`tests/test_photovoltaic_tenant_boundaries.py`. Reviewer obrigatório.

**Etapa D — endpoint de retorno financeiro.** Depende de A, B e C.
`src/mplacas/intelligence/financial_return_service.py` mais
`GET /energy/financial-return/latest` em `src/mplacas/intelligence/router.py`, com o enum
`FinancialReturnUnavailableReason` e as regras dos itens 5 e 6. Testes conforme a seção
Validação, incluindo obrigatoriamente cobertura parcial e os três motivos de
indisponibilidade. Reviewer obrigatório.

**Etapa E — frontend.** Depende de D. Parser do contrato em
`frontend/src/lib/dashboard/contracts.ts`, seção de retorno financeiro com barra de
progresso em `brand-primary`, rótulo de cobertura, projeção rotulada como projeção,
diálogo de cadastro do CAPEX visível apenas para ADMIN. Testes de componente mais
`npm run build` com verificação das classes no CSS gerado. Sem reviewer.
