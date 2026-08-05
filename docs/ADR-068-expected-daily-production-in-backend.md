# ADR-068 — Produção diária esperada calculada no backend

## Status

Aceito — 2026-08-05. Fórmula compartilhada entre `/photovoltaic/summary` e `/energy/anomalies/latest`
aprovada; decisão de ignorar (não honrar) o parâmetro depreciado durante a janela de compatibilidade
aprovada, já que a fórmula é preservada e o valor devolvido seria o mesmo; escopo negativo (não
resolve P1-02, rerrotulagem, nesta frente) confirmado.

A decisão de negócio ("o cálculo sai do cliente") já foi aprovada pelo usuário. Este ADR
formaliza os detalhes técnicos e passa a **Aceito** após a confirmação deles.

## Contexto

O ADR-012 estabelece, em uma linha que não admite leitura ambígua: *"Regras e cálculos
energéticos continuam exclusivamente no backend determinístico."* O ADR-066 cita esse
trecho textualmente ao justificar por que o cálculo de emissões evitadas nasceu no
servidor.

A auditoria de UI/UX de 2026-08-04 (`docs/UI_UX_AUDIT_2026-08-04.md`, achado **P1-01**,
problema comprovado) encontrou uma violação direta dessa regra:

```ts
// frontend/src/lib/dashboard/photovoltaic-contracts.ts:274
const kwh = dcCapacityKwp * clearSkyPoaKwhM2 * performanceRatio
```

`deriveExpectedDailyProduction` (`photovoltaic-contracts.ts:251-280`) multiplica
`performance.dc_capacity_kwp` × `baseline.clear_sky_poa_p90_kwh_m2` ×
`baseline.baseline_median_performance_ratio` — três grandezas que
`GET /photovoltaic/summary` (ver ADR-065) já devolve prontas — para produzir a produção
diária esperada da usina.

O agravante é o caminho de volta. `DashboardPage.tsx:120` guarda o resultado e
`DashboardPage.tsx:151-153` o **reenvia ao servidor** na query string:

```
GET /energy/anomalies/latest?plant_id=…&expected_daily_production_kwh=<calculado no browser>&days=90
```

`intelligence/router.py:310` declara esse parâmetro como `Decimal = Query(..., gt=0)` e o
repassa a `analyze_recent_persisted_anomalies`, que o usa como referência para classificar
NORMAL / ATENÇÃO / ANOMALIA / CRÍTICO em **cada um dos últimos 90 dias**
(`anomaly_service.py:146,157`). Ou seja: hoje o cliente determina o valor de referência
contra o qual o backend julga a usina. Um número exibido na tela não é auditável a partir
do servidor, e a severidade de 90 dias é função de uma expressão JavaScript.

Nada disso é um bug de cálculo — a fórmula no cliente está correta e é numericamente
equivalente a `final_yield_kwh_per_kwp × dc_capacity_kwp` para um dia representativo da
estação. O problema é **de lugar**, e é exatamente por isso que a correção pode ser feita
sem alterar nenhum número exibido.

Duas coisas que este ADR deliberadamente **não** decide, para manter o risco contido:

- **Não redefine a fórmula.** O achado P1-02 da mesma auditoria observa, com razão, que uma
  expectativa derivada do envelope de céu limpo P90 é sistematicamente otimista quando
  aplicada a 90 dias que atravessam estações e dias nublados. Corrigir isso é a Etapa 2.3
  do roadmap, muda o significado de um número já publicado em produção, e exige decisão
  própria do usuário. Este ADR **move** o cálculo; não o altera.
- **Não toca em `POST /alerts/run` nem em `POST /orchestration/run`**, que também recebem
  `expected_daily_production_kwh` como query param (`alerts/router.py:32`,
  `orchestration/router.py:36`). Ali o valor vem de
  `settings.cloud_job_expected_daily_production_kwh` (`cloud_jobs.py:405,470`), isto é, de
  configuração operacional do próprio deploy — não de um browser. É outro problema, com
  outro dono, e será tratado separadamente se valer a pena.

**Premissa de consumidores da API, verificada:** o único cliente HTTP do backend é
`frontend/` deste mesmo repositório (o único módulo que chama `apiFetch` é
`frontend/src/lib/api.ts`), somado ao Cloud Run Job, que só usa `/orchestration` e
`/alerts` — fora do escopo acima. Não existe SDK publicado, app móvel, integração de
terceiro nem contrato externo versionado. Isso é o que torna um prazo curto de depreciação
defensável.

## Decisão

### 1. Uma função pura nova, versionada, em `photovoltaic/expected_production.py`

Módulo novo `src/mplacas/photovoltaic/expected_production.py`:

```python
EXPECTED_PRODUCTION_MODEL_VERSION = "MPLACAS_EXPECTED_DAILY_PRODUCTION_V1"
EXPECTED_PRODUCTION_NATURE = "SEASONAL_CLEAR_SKY_P90_ENVELOPE"

@dataclass(frozen=True, slots=True)
class ExpectedDailyProduction:
    expected_daily_production_kwh: Decimal
    dc_capacity_kwp: Decimal
    clear_sky_poa_p90_kwh_m2: Decimal
    baseline_median_performance_ratio: Decimal
    model_version: str
    nature: str

def calculate_expected_daily_production(
    *,
    dc_capacity_kwp: Decimal | None,
    clear_sky_poa_p90_kwh_m2: Decimal | None,
    baseline_median_performance_ratio: Decimal | None,
) -> ExpectedDailyProduction | None: ...
```

Sem I/O, sem sessão, sem ORM — três `Decimal` entram, um resultado ou `None` sai. Devolve
`None` quando qualquer entrada é nula ou não positiva, ou quando o produto não é positivo.

**Por que módulo novo e não dentro de `seasonal_baseline.py`.** `seasonal_baseline.py`
possui um modelo **persistido**, cuja versão `MPLACAS_SEASONAL_PR_BASELINE_V1` é gravada em
`seasonal_pv_baseline_results` e filtra leituras (`read_service.py`). A expectativa é uma
grandeza **derivada em tempo de leitura**, composta de dois registros de tabelas
diferentes, e a Etapa 2.3 provavelmente vai mudar sua fórmula. Se ela morasse sob a versão
do baseline, mudá-la exigiria bumpar `BASELINE_MODEL_VERSION` e invalidar linhas
persistidas corretas. Versão própria isola as duas evoluções.

O campo `nature` viaja sempre, no mesmo espírito dos campos `*_nature` do ADR-065 seção 3:
ele diz que essa expectativa vem de um envelope de céu limpo P90 sazonal, não de uma
previsão meteorológica do dia. É o gancho de contrato que a Etapa 2.3 usará para rotular o
número honestamente na UI, sem precisar de outro ADR de contrato.

### 2. Um único resolvedor com I/O, em `photovoltaic/read_service.py`

```python
@dataclass(frozen=True, slots=True)
class ExpectedProductionResolution:
    expected: ExpectedDailyProduction | None
    unavailable_reason: str | None
    reference_complete_on: date | None

async def resolve_expected_daily_production(
    session: AsyncSession, *, plant_id: uuid.UUID, today: date | None = None
) -> ExpectedProductionResolution: ...
```

Carrega o registro de performance mais recente e o baseline sazonal mais recente reusando
`get_latest_performance` e `get_latest_baseline` já existentes, chama a função pura da
seção 1 e, quando não há resultado, deriva o motivo com
`_derive_baseline_unavailable_reason` — a mesma função que já produz
`NO_PERFORMANCE_HISTORY` / `REFERENCE_YEAR_INCOMPLETE` / `INSUFFICIENT_SEASONAL_SAMPLES`
(ADR-065 seção 6). **Nenhum código novo de motivo de indisponibilidade é inventado.**

Como o resto de `read_service.py`, a função pressupõe que o chamador já abriu a sessão e
aplicou `set_principal_context`; ela não contém autorização própria.

**Este é o ponto exato de reuso exigido pelo roadmap.** `/energy/anomalies/latest` chama
`resolve_expected_daily_production`. `/photovoltaic/summary` **não** a chama: `get_summary`
já carregou os dois registros e o motivo de indisponibilidade do baseline na mesma sessão,
então ele chama diretamente `calculate_expected_daily_production` (a função pura) com os
objetos que tem em mãos. Os dois endpoints compartilham a fórmula; nenhum dos dois executa
uma query a mais por causa desta decisão.

Um quarto código de indisponibilidade é introduzido: **`INCOMPLETE_EXPECTATION_INPUTS`**,
usado quando existe baseline defensável mas alguma das três entradas veio nula ou não
positiva. Hoje o frontend mapeia esse ramo defensivo para `NO_PERFORMANCE_HISTORY`
(`photovoltaic-contracts.ts:271`), que é uma afirmação falsa — existe histórico, ele só
está incompleto. O backend passa a dizer a verdade.

### 3. `GET /photovoltaic/summary` ganha quatro campos, aditivamente

Acrescentados no nível raiz do payload (não dentro de `baseline`, porque a grandeza compõe
`performance.dc_capacity_kwp` com dois campos de `baseline`):

```json
{
  "expected_daily_production_kwh": "38.412",
  "expected_daily_production_model_version": "MPLACAS_EXPECTED_DAILY_PRODUCTION_V1",
  "expected_daily_production_nature": "SEASONAL_CLEAR_SKY_P90_ENVELOPE",
  "expected_daily_production_unavailable_reason": null
}
```

`Decimal` como string e campos nullable sempre presentes, jamais omitidos — ADR-065 seção
3. Quando indisponível, os três primeiros são `null` e o quarto carrega o código.
`/summary` continua sempre 200 (ADR-065 seção 5).

O valor é quantizado com `ROUND_HALF_UP` em `0.001` kWh, seguindo `seasonal_baseline._round`.
Isso introduz uma diferença de casas decimais em relação ao float que o browser calcula
hoje; a seção Validação fixa que a diferença é irrelevante para a classificação.

Este passo é **puramente aditivo**: nenhum campo existente muda de nome, tipo ou valor, e
nenhum cliente precisa mudar junto.

### 4. O frontend passa a ler, e `deriveExpectedDailyProduction` é removida

`photovoltaic-contracts.ts` passa a parsear os quatro campos novos em
`parsePhotovoltaicSummary` e a expor o tipo `ExpectedDailyProduction` preenchido a partir
deles. A função `deriveExpectedDailyProduction`, seu bloco de testes
(`photovoltaic-contracts.test.ts:172-210`) e a referência em comentário de
`yield.ts:8` deixam de existir.

`BaselineUnavailableReason` ganha `INCOMPLETE_EXPECTATION_INPUTS` e
`baselineUnavailableMessage` ganha o caso correspondente — a UI nunca mostra um card vazio
sem motivo.

**A partir deste ponto, `photovoltaic-contracts.ts` não contém nenhuma multiplicação de
grandezas energéticas.** A única multiplicação que permanece no arquivo é
`ratioToPercent` (`× 100`), que é conversão de unidade de uma razão adimensional, não
composição de grandezas físicas — a distinção está escrita no critério de aceite da seção 7.

### 5. `GET /energy/anomalies/latest` resolve a expectativa internamente

A assinatura em `intelligence/router.py:310` passa de

```python
expected_daily_production_kwh: Decimal = Query(..., gt=0)
```

para

```python
expected_daily_production_kwh: Decimal | None = Query(default=None, gt=0, deprecated=True)
```

e o handler chama `resolve_expected_daily_production` dentro da sessão já contextualizada,
**antes** de `analyze_recent_persisted_anomalies`. `anomaly_service.py` não muda: continua
recebendo um `Decimal` positivo e continua levantando `ValueError` para valores não
positivos.

**O parâmetro recebido é aceito e validado, mas ignorado.** Não há janela em que um valor
vindo do cliente volte a determinar a severidade — seria manter aberta, por semanas, a
exata vulnerabilidade que o ADR fecha. A depreciação preserva **compatibilidade de
requisição**, não semântica de valor: um frontend em cache que ainda envie o parâmetro
recebe 200 e um resultado calculado pelo servidor. Como a seção 1 preserva a fórmula, esse
resultado é o mesmo número que o cliente teria enviado, a menos de arredondamento.

Quando a expectativa não pode ser resolvida, o endpoint devolve **404** com
`detail="no expected daily production for this plant: <REASON>"`, alinhado ao 404 que
`AnomalyDataNotFoundError` já produz na mesma rota, e portanto já tratado por
`classifyAnomalyErrorStatus` no cliente. O frontend, de todo modo, continua não chamando a
rota quando `/photovoltaic/summary` já disse que a expectativa é indisponível.

`intelligence/` passa a importar de `photovoltaic/` — precedente já existente em
`climate/collection_service.py`, `orchestration/daily_pipeline.py` e
`retention/timeseries_service.py`.

### 6. Prazo de depreciação do parâmetro de query

O parâmetro `expected_daily_production_kwh` de `/energy/anomalies/latest` é removido
**no segundo release após aquele que entregar a seção 5, e nunca antes de 30 dias corridos
do respectivo deploy** — o que ocorrer por último.

Justificativa do prazo curto: o único consumidor é o frontend deste repositório, servido
pelo mesmo deploy, e o risco residual é exclusivamente um browser com bundle antigo em
cache. Trinta dias cobrem folgadamente esse cenário. Não há contrato externo a honrar.

A remoção entra como item de checklist rastreável em
`docs/UI_UX_IMPLEMENTATION_ROADMAP_2026-08-04.md`, não como TODO no código. Enquanto
existir, o parâmetro fica marcado `deprecated=True`, o que o exibe riscado no OpenAPI.

### 7. Critério de aceite, mecanicamente verificável

Dois testes, não prosa:

1. **Nenhuma chamada do frontend envia expectativa de produção ao servidor.** Teste em
   `frontend/src/lib/dashboard/` que varre `frontend/src/**/*.{ts,tsx}` e falha se
   qualquer arquivo contiver a substring `expected_daily_production_kwh` na construção de
   uma URL. Busca textual em vez de inspeção de chamada porque a propriedade a proteger é
   sintática e permanente, e um teste que qualquer pessoa consegue ler vale mais aqui que
   um mock elaborado.
2. **`photovoltaic-contracts.ts` não compõe grandezas energéticas.** Teste que afirma que
   o módulo não exporta `deriveExpectedDailyProduction` e que o arquivo não contém nenhuma
   multiplicação envolvendo `dc_capacity_kwp`, `clear_sky_poa` ou `performance_ratio`.
   `ratioToPercent` é a única multiplicação permitida e é explicitamente listada como
   exceção no próprio teste, com comentário.

### 8. Plano de implementação em etapas verificáveis

Cada etapa fecha com CI verde (ruff, mypy, pytest, lint e testes do frontend) e é
mergeável isoladamente. Nenhuma etapa depende de uma etapa posterior para não quebrar
produção.

**Etapa A — função pura + resolvedor (backend, sem mudança de contrato).**
Criar `photovoltaic/expected_production.py` (seção 1) e
`resolve_expected_daily_production` em `read_service.py` (seção 2). Nenhum router muda.
Testes: tabela de casos da função pura, incluindo cada entrada nula, zero e negativa;
teste do resolvedor devolvendo cada um dos quatro códigos de indisponibilidade.
*Reviewer: não.* Código novo, puro, sem superfície HTTP e sem query nova.

**Etapa B — expor em `/photovoltaic/summary` (aditivo).**
`get_summary` passa a chamar a função pura com os registros que já carregou; o router
serializa os quatro campos da seção 3. Testes: campos presentes com valor quando há
baseline; os quatro presentes com `null` mais o código de motivo quando não há; teste de
regressão afirmando que **o número devolvido é igual ao que `deriveExpectedDailyProduction`
produzia** para o mesmo payload, a menos do arredondamento em `0.001`; teste afirmando que
`get_summary` não executa nenhuma query além das que já executava.
*Reviewer: não obrigatório* — ver a ressalva de roteamento logo abaixo.

**Etapa C — frontend lê o campo, `deriveExpectedDailyProduction` é removida.**
Seção 4, mais os dois testes da seção 7. Etapa puramente de cliente.
*Reviewer: não.*

**Etapa D — `/energy/anomalies/latest` resolve internamente e deprecia o parâmetro.**
Seção 5. Testes: expectativa resolvida internamente com o parâmetro ausente; o mesmo
resultado com o parâmetro presente e com um valor **propositalmente errado**, provando que
ele é ignorado; 404 com o código de motivo quando indisponível; e teste de fronteira de
tenant na rota, no molde de `tests/test_alerts_tenant_boundaries.py`, garantindo que a
leitura nova das tabelas fotovoltaicas dentro de um handler de `intelligence` respeita o
escopo de organização.
**Reviewer: sim, obrigatório.**

**Etapa E — remoção do parâmetro**, no prazo da seção 6. Uma linha de assinatura e a
atualização dos testes que ainda o enviarem.
*Reviewer: não.*

**Ressalva de roteamento.** O roadmap marcou "Reviewer: sim" para os passos 1 e 3 da Etapa
3.1. Pela regra do `CLAUDE.md`, reviewer é obrigatório em billing, auth, credentials,
organizations, audit e migrations. Concordo com a marcação do passo 3 (aqui, Etapa D): ele
introduz uma leitura de tabelas de outro domínio **dentro de um handler existente**, e um
`set_principal_context` ausente ou um `plant_id` trocado nesse ponto é falha de isolamento
entre organizações — categoria coberta pela regra. Já para o passo 1 (aqui, Etapa B) **o
roadmap superestimou o risco**: com o desenho da seção 2, a Etapa B não abre sessão nova,
não adiciona query, não muda autorização e não altera nenhum campo existente — é
serialização adicional de dados que o handler já carregou sob o mesmo `ReadPlant`. Reviewer
aí seria ritual, não controle. Fica registrada a condição de reversão dessa avaliação: **se
o worker precisar adicionar qualquer query nova no caminho de `/photovoltaic/summary`, a
Etapa B volta a exigir reviewer.**

## Consequências

### Positivas

- Fecha a violação do ADR-012 comprovada em P1-01, na causa e não no sintoma: depois da
  Etapa D não existe caminho pelo qual um cliente influencie a classificação de severidade.
- O número exibido passa a ser auditável a partir do servidor, e carrega uma versão de
  modelo (`MPLACAS_EXPECTED_DAILY_PRODUCTION_V1`) que permite saber com que fórmula um
  valor foi produzido — impossível hoje, em que a fórmula é a versão do bundle JavaScript
  que o browser tinha em cache.
- Zero migration, zero mudança de modelo de dados, zero mudança no pipeline diário.
- Nenhum número muda de valor. A mudança é de lugar, o que a torna verificável por um teste
  de equivalência direto (Etapa B) — a forma mais barata de provar ausência de regressão.
- Prepara a Etapa 2.3 (rótulo honesto da expectativa) sem antecipá-la: o campo `nature` já
  chega ao cliente, então mudar a fórmula depois será uma mudança de backend com um bump de
  versão, sem novo ADR de contrato.
- `INCOMPLETE_EXPECTATION_INPUTS` corrige uma mentira pequena que o frontend conta hoje.

### Negativas

- **Mais um round-trip conceitual para a UI.** A expectativa deixa de ser derivável
  offline; se `/photovoltaic/summary` falhar, o cliente não tem como estimar nada. Aceito —
  e é precisamente o efeito desejado: um número que o cliente não pode derivar é um número
  que ele não pode falsificar.
- **Um módulo e uma versão de modelo a mais para manter.** Cinco constantes
  `MPLACAS_*_V<N>` passam a seis, cada uma com seu próprio ciclo de vida.
- **Acoplamento novo de `intelligence/` a `photovoltaic/`.** Há precedente em três módulos,
  mas é mais uma aresta no grafo de dependências, e um endpoint de anomalias que agora
  falha se a cadeia fotovoltaica não tiver produzido baseline.
- **Um contrato depreciado convivendo com o novo por até dois releases.** Durante a janela,
  `/energy/anomalies/latest` aceita um parâmetro que ignora — estado transitório
  intrinsecamente confuso para quem lê o código sem o ADR. Mitigado por `deprecated=True`,
  por um teste que **afirma** que o valor é ignorado, e por um prazo curto.
- **A quantização em `0.001` kWh muda os últimos dígitos** em relação ao float do browser.
  Numericamente irrelevante, mas é uma diferença real que um teste precisa fixar em vez de
  fingir que não existe.
- **A expectativa continua otimista.** Este ADR move um número que a auditoria já
  classificou como sistematicamente otimista para janelas longas (P1-02). Mover primeiro e
  corrigir depois é escolha consciente de sequenciamento: separa uma mudança de arquitetura
  sem efeito visível de uma mudança de significado com efeito visível. Quem ler este ADR
  isolado deve saber que ele **não** resolve P1-02.

## Validação

1. Testes unitários da função pura: caso feliz, cada entrada nula, cada entrada zero ou
   negativa, e produto não positivo — todos devolvendo `None`.
2. Teste dos quatro códigos de indisponibilidade do resolvedor, incluindo
   `reference_complete_on` no caso `REFERENCE_YEAR_INCOMPLETE`.
3. **Teste de equivalência (o mais importante):** para um payload representativo, o
   `expected_daily_production_kwh` do backend é igual ao produto que
   `deriveExpectedDailyProduction` produzia, com tolerância de `0.001` kWh. Escrito na
   Etapa B, enquanto a função antiga ainda existe para comparar.
4. Teste de que uma diferença de arredondamento de `0.001` kWh não altera nenhuma
   classificação de severidade em `analyze_recent_persisted_anomalies`, salvo em um valor
   exatamente sobre o limiar — caso que o teste enumera explicitamente.
5. Teste de que `/photovoltaic/summary` não passou a executar query adicional.
6. Teste de que `/energy/anomalies/latest` devolve resultado idêntico com o parâmetro
   ausente, presente e correto, e presente e **errado** — provando que é ignorado.
7. Teste de fronteira de tenant em `/energy/anomalies/latest` após a Etapa D: principal da
   organização A recebe 404 ao pedir `plant_id` da organização B.
8. Os dois testes de critério de aceite da seção 7.
9. CI verde nas cinco etapas: ruff, mypy, pytest, lint e testes do frontend.

## Alternativas descartadas

- **Persistir `expected_daily_production_kwh` em coluna ou tabela nova.** Daria histórico e
  permitiria reconstruir a expectativa vigente em qualquer data passada. Descartado: exige
  migration e mudança no pipeline diário para uma grandeza que é uma multiplicação de três
  campos já persistidos, computável em tempo de leitura sem custo de query. Se algum dia
  for preciso auditar a expectativa retroativamente, este é o caminho — e será decisão
  explícita do usuário.
- **Honrar o parâmetro de query durante a janela de depreciação**, ignorando-o só na
  remoção. Mais conservador em aparência, mas manteria por semanas exatamente a
  vulnerabilidade que o ADR existe para fechar, e tornaria o comportamento do endpoint
  dependente de qual bundle o browser carregou. Descartado.
- **Remover o parâmetro de uma vez, junto com a Etapa D.** Tecnicamente viável dado que só
  há um consumidor, e tentador pela simplicidade. Descartado por margem estreita: um
  browser com bundle antigo receberia 422 de validação em vez de um gráfico, e o custo de
  manter uma linha depreciada por 30 dias é menor que o de uma tela quebrada para o único
  usuário do sistema.
- **Recalcular a expectativa dentro de `anomaly_service.py`, por dia.** Seria a expectativa
  *correta* — uma por dia, em vez de uma constante replicada 90 vezes. Descartado aqui por
  ser exatamente P1-02: muda o significado de um número publicado, e este ADR não pode
  fazer isso escondido dentro de uma mudança de arquitetura.
- **Colocar a fórmula em `seasonal_baseline.py`**, sob `BASELINE_MODEL_VERSION`. Descartado
  pelo argumento de versionamento da seção 1: acoplaria a evolução de uma grandeza derivada
  em tempo de leitura à versão de um modelo persistido.
- **Devolver a expectativa dentro do bloco `baseline` de `/summary`.** Mais arrumado à
  primeira vista, mas a grandeza depende de `performance.dc_capacity_kwp`; colocá-la sob
  `baseline` sugeriria que ela é um campo do registro de baseline, que ela não é.

## Reversibilidade

Alta, e assimétrica por etapa — o que é a razão de o plano ter cinco etapas e não uma.

Até a Etapa B inclusive, a reversão é remover quatro chaves do payload e um arquivo novo:
nenhum cliente depende deles ainda. Depois da Etapa C, reverter exige restaurar
`deriveExpectedDailyProduction` — recuperável do histórico do git, mas é o ponto a partir
do qual a reversão deixa de ser trivial. Depois da Etapa D, reverter significa voltar a
confiar num valor vindo do cliente, o que não deve ser feito por conveniência operacional:
se `resolve_expected_daily_production` falhar em produção, a resposta certa é 404 na rota
de anomalias (o resto do dashboard segue funcionando, como já ocorre hoje quando não há
baseline), não reabrir o parâmetro.

O ponto de extensão para a Etapa 2.3 e para qualquer mudança futura de fórmula é
`expected_production.py::calculate_expected_daily_production`, com bump de
`EXPECTED_PRODUCTION_MODEL_VERSION` e um novo valor de `nature`. Nenhum outro arquivo
precisa mudar para trocar a definição de "produção esperada" daqui em diante — que é, no
fundo, o ganho estrutural que justifica este ADR.
