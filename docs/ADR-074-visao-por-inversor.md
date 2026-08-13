# ADR-074 — Visão por inversor (estado operacional por device)

## Status

**Proposto** (2026-08-12). Base: `HEAD a8e2fe4`.
Tarefa T1 de `docs/PLANO_EXECUCAO_AUDITORIA_FRONTEND_2026-08-12.md` (recomendação nº 1 da
auditoria de frontend).

Dois pontos exigem confirmação do usuário antes da implementação — marcados **⚠ CONFIRMAR**
nas Decisões 6 e 7. O restante pode ser implementado assim que este ADR for aceito.

## Contexto

### O que o backend já sabe e nunca conta

O backend calcula, todo dia, produção e rendimento **por inversor**, e avalia cada um contra a
mediana histórica dele mesmo:

| Fato | Evidência |
|---|---|
| `Device` é entidade de primeira classe (FK `plant_id` indexada, `serial_number` único por provider, capacidades) | `src/mplacas/db/models.py:107-138` |
| `DailyEnergy` é por inversor, uma linha por `(device_id, production_date)` | `src/mplacas/db/models.py:141-146` |
| Produção e rendimento por inversor, com `production_kwh: None` significando "não reportou" (≠ produziu zero) | `src/mplacas/alerts/production_alert.py:122-138` |
| Rendimento relativo à **própria** mediana + flag `dropped` | `src/mplacas/alerts/production_alert.py:158-164` |
| Coleta que parte de `Device`, não de `DailyEnergy` (ver Restrição 1) | `src/mplacas/alerts/production_alert.py:825-892` |
| Medianas por device em 2 queries, independente do tamanho da frota | `src/mplacas/alerts/production_alert.py:895-961` |
| Avaliação por device (pura, sem I/O) | `src/mplacas/alerts/production_alert.py:495-513` |

Essa informação tem **exatamente uma saída**: `_device_lines`
(`src/mplacas/alerts/production_alert.py:635-688`), que a converte em texto HTML de Telegram.
`alerts/router.py` expõe apenas `POST /run` (`src/mplacas/alerts/router.py:56`) — não há
endpoint de consulta. Quem não usa o bot nunca soube qual inversor caiu.

### O que o frontend mostra hoje

Nada nomeia equipamento. Não há uma única ocorrência da palavra `device` em
`frontend/src/lib/` (verificado em 2026-08-12: `grep -rn "device" frontend/src/lib/` → vazio).
O mais próximo que existe é o **agregado**: `ReportingAvailabilityCard.tsx:30` mostra
`reporting_availability_ratio`, e o tile "Disponibilidade dos dados" em
`frontend/src/pages/dashboard/TechnicalPage.tsx:173-178` mostra o mesmo número com o rótulo
"reporte dos devices". Numa usina de 2 inversores, o usuário lê **"50%"** e não tem como saber
*qual* metade parou. A pergunta está na tela; a resposta existe no backend e não aparece.

### O que já está exposto por HTTP (e não precisa ser reconstruído)

`GET /plants/{plant_id}/technical-configuration` (`src/mplacas/plants/router.py:232-247`,
autorização `ReadPlantPath`) já devolve `devices[]` com `device_id`, `serial_number`,
`dc_capacity_kwp` e `ac_capacity_kw` (`src/mplacas/plants/router.py:220-228`). Ou seja: a
**identidade** e a **configuração** do inversor já são leitura autorizada do produto. O que não
existe em lugar nenhum é **estado operacional por inversor**. Esta é a lacuna que o ADR fecha —
e é uma lacuna estreita, não um módulo inteiro a inventar.

### Restrições de domínio inegociáveis

1. **Inversor sem comunicação precisa aparecer.** Docstring literal de `_gather_device_metrics`
   (`src/mplacas/alerts/production_alert.py:832-838`): *"One entry per inverter registered on the
   plant, target day or not. A device that lost communication for the whole day has no
   DailyEnergy row — it must still show up (as 'sem dados') instead of silently vanishing. In a
   two-inverter plant that is the single most serious failure mode there is, and it must never be
   the one the message can't mention."*
   A consulta parte de `Device` (`:840-846`) e cruza com `DailyEnergy` numa **segunda** query
   (`:848-858`). Qualquer implementação que parta de `DailyEnergy` faz o inversor mudo
   desaparecer — reintroduzindo exatamente a falha que o código existente evita de propósito.
2. **Rendimento de um inversor só se compara com a mediana dele mesmo**
   (`src/mplacas/alerts/production_alert.py:136-138`: *"never another device's, since inverters
   have different chronic baselines"*). Nenhum ranking entre inversores, nenhuma ordenação por
   desempenho, nenhum "melhor/pior" — nem no payload, nem na tela.
3. **"Sem dados" nunca vira zero.**
4. **Escala real: ~2 inversores por usina.** Sem paginação, virtualização, busca ou filtro.
5. **Convenção de leitura do projeto:** 200 sempre dentro do escopo, indisponibilidade como campo
   + motivo (`docs/PLANO_EXECUCAO_AUDITORIA_FRONTEND_2026-08-12.md` §2.2; padrão em
   `src/mplacas/photovoltaic/router.py:112-122`). Isso conflita com o `raise` de
   `gather_production_alert_metrics` (`:200-203`) — resolvido na Decisão 4.
6. **Isolamento multi-tenant.** `devices` está sob RLS por `plant_id`
   (`migrations/versions/20260802_0040_enable_postgresql_rls.py:39`, predicado em `:66-74`) e
   `daily_energy` sob RLS via `devices → plants` (`:56`, `:75-83`). O handler precisa de
   `set_principal_context` — sem ele a policy não tem contexto e o isolamento não acontece.
7. **Cálculo é do backend.** O frontend apresenta.

## Decisão

### 1. Superfície nova: módulo `devices/`, com o cálculo movido para lá

Cria-se `src/mplacas/devices/` no formato canônico de leitura do projeto
(`src/mplacas/photovoltaic/router.py:1-7` descreve esse formato: router fino → `read_service.py`
→ `serialization.py`, nenhum cálculo no router):

```
src/mplacas/devices/
  metrics.py         # o cálculo, MOVIDO de alerts/production_alert.py (Decisão 2)
  read_service.py    # composição da leitura + resolução do dia alvo
  serialization.py   # dict puro, Decimal como str
  router.py          # GET /devices/daily-status
```

Registrado em `src/mplacas/main.py` junto dos demais (`src/mplacas/main.py:149-164`).

**Direção de dependência decidida: `alerts → devices`.** O módulo de notificação passa a
importar o cálculo de estado do ativo, nunca o contrário. Um módulo de leitura que dependesse de
`alerts` para saber o estado de um inversor seria a inversão errada, e é o principal motivo para
não escolher a alternativa (a) abaixo.

**Alternativas avaliadas e recusadas:**

| Alternativa | Por que não |
|---|---|
| (a) `alerts/read_service.py` | `alerts/` hoje significa **despacho de notificação**: o router só tem `POST /run` (`alerts/router.py:56`) e a única tabela é `alert_delivery_records`, um registro de *entrega* (`src/mplacas/alerts/db_models.py`, ver T3 do plano). Leitura de estado de ativo não é notificação. Além disso, a T3 vai adicionar uma superfície de leitura *de alertas* em `alerts/` — misturar as duas no mesmo módulo confunde permanentemente "o que o alerta disse" com "como o equipamento está" |
| (b) `photovoltaic/` | É a cadeia de **modelagem** versionada (ADR-065): POA, PR, baseline sazonal, perdas — resultados persistidos com `model_version`. A visão por inversor é medição bruta + uma mediana, sem modelo e sem versão. Pendurá-la em `/photovoltaic/summary` misturaria uma leitura observacional não-versionada num payload cuja garantia é justamente a versão do modelo (`photovoltaic/serialization.py:53-59`) |
| (c) `intelligence/` | É a leitura derivada de energia a nível de **usina** (`/energy/executive`, `/energy/anomalies`, `/energy/financial-return`). Nenhum dos seus serviços tem device como unidade de saída; entrar ali dilui a fronteira sem ganhar nada |
| (d) `plants/router.py` | Atrai por já expor `devices[]` (`plants/router.py:232-247`) e por ser RESTfulmente correto (`/plants/{id}/devices/...`). Recusado por dois motivos concretos: o arquivo é superfície de **configuração**, mistura GET/PATCH com auditoria e faz query inline no router — ou seja, **não segue** o padrão canônico de leitura exigido pelo §2.1 do plano; e as leituras de dashboard do projeto usam `?plant_id=` + `ReadPlant`, não path param |

**Custo aceito:** três módulos passam a tocar `Device` (`plants/` = configuração, `photovoltaic/`
= insumo de performance em `photovoltaic/performance_service.py:67-95`, `devices/` = estado).
Isso já era verdade para dois deles; o terceiro é o que dá nome ao conceito.

### 2. Reuso sem duplicação: mover o cálculo, nunca copiar

**Proibido em qualquer hipótese:** uma segunda implementação da mediana de rendimento. Ela existe
uma vez, em `_device_rendimento_medians` (`src/mplacas/alerts/production_alert.py:895-961`), e
continua existindo uma vez.

O que se move de `alerts/production_alert.py` para `devices/metrics.py`, **sem alterar uma linha
de corpo de função**:

| Origem | Destino | Nome |
|---|---|---|
| `DeviceProductionMetrics` (`:122-138`) | `devices/metrics.py` | igual |
| `DeviceYieldAssessment` (`:158-164`) | `devices/metrics.py` | igual |
| `_gather_device_metrics` (`:825-892`) | `devices/metrics.py` | `gather_device_metrics` (público) |
| `_assess_devices` (`:495-513`) | `devices/metrics.py` | `assess_devices` (público) |
| `_device_rendimento_medians` (`:895-961`) | `devices/metrics.py` | segue privado |
| `DEVICE_NORMAL_THRESHOLD` (`:91`) | `devices/metrics.py` | igual |
| `MINIMUM_RENDIMENTO_SAMPLE_DAYS` (`:101`) | `devices/metrics.py` | igual |
| `LOOKBACK_DAYS` (`:71`) | `devices/metrics.py` | `RENDIMENTO_LOOKBACK_DAYS` |

`alerts/production_alert.py` passa a importar os oito símbolos. Para as duas funções que ficam em
`alerts/` e usam a janela (`_irradiation_median:739`, `_plant_rendimento_median:767`), mantém-se
`LOOKBACK_DAYS = RENDIMENTO_LOOKBACK_DAYS` como **alias de uma linha** — nunca um segundo `30`
literal. O projeto já carrega esse tipo de constante duplicada amarrada só por comentário
(`alerts/production_alert.py:70-71`, `intelligence/anomaly_service.py:29-30`,
`reports/daily_digest.py:40`); esta decisão não amplia essa dívida.

**Este movimento é uma etapa isolada, sem nenhuma outra mudança junto.** A prova de que nada
quebrou é `tests/test_production_alert.py` (29 testes, 984 linhas) passando com **uma única
alteração: a linha de import** — hoje o arquivo importa `DeviceProductionMetrics` de
`alerts.production_alert` (`tests/test_production_alert.py:22-31`) e passa a importar de
`devices.metrics`. Se qualquer outro trecho desse arquivo precisar mudar, o movimento não foi
mecânico e deve ser revertido antes de seguir.

### 3. Contrato do payload

`GET /devices/daily-status?plant_id={uuid}` · autorização `ReadPlant` · **200 sempre** dentro do
escopo.

**Nome recusado:** `/devices/latest`. No projeto, `/latest` nomeia o registro mais recente de um
resultado modelado (`/photovoltaic/performance/latest`, `/energy/executive/latest`); aqui
devolvemos o **elenco completo** de inversores num dia, que é outra forma.
`/photovoltaic/summary` (`photovoltaic/router.py:112`) já precedenta nome descritivo para leitura
composta.

Envelope:

```jsonc
{
  "plant_id": "…",
  "observation_date": "2026-08-11",              // dia mais recente com QUALQUER DailyEnergy da usina
  "observation_date_unavailable_reason": null,   // "NO_PRODUCTION_HISTORY" quando não há dia nenhum
  "irradiation_kwh_m2": "5.12",                  // do dia acima
  "irradiation_unavailable_reason": null,        // "NO_CLIMATE_OBSERVATION"
  "device_count": 2,
  "reporting_device_count": 1,
  "device_normal_threshold": "0.85",             // DEVICE_NORMAL_THRESHOLD, ver justificativa abaixo
  "units": {
    "production": "kWh",
    "irradiation": "kWh/m2",
    "rendimento": "kWh/(kWh/m2)",
    "relative_to_own_median": "ratio",
    "relative_to_own_median_deviation": "percent"
  },
  "devices": [ … ]
}
```

Por device, na ordem estável de `Device.serial_number` — a mesma de
`alerts/production_alert.py:845` e de `plants/router.py:205` —, **nunca ordenado por desempenho**
(Restrição 2):

```jsonc
{
  "device_id": "…",
  "serial_number": "…",
  "reporting_status": "REPORTED" | "NOT_REPORTED",
  "production_kwh": "12.480",                    // null se NOT_REPORTED — nunca 0
  "last_reported_date": "2026-08-11",            // null se o device nunca reportou
  "rendimento": "2.437",                         // null quando não há como dividir
  "rendimento_median": "3.390",                  // a mediana DESTE device
  "relative_to_own_median": "0.719",             // rendimento / rendimento_median
  "relative_to_own_median_deviation_percent": "-28.1", // (relative_to_own_median − 1) × 100 — ver correção de rota abaixo
  "yield_status": "NORMAL" | "DROPPED" | "UNKNOWN",
  "yield_unavailable_reason": null | "NOT_REPORTED" | "NO_IRRADIATION_READING" | "INSUFFICIENT_DEVICE_HISTORY"
}
```

`Decimal` serializa como `str`, datas em ISO-8601, campos nulos sempre presentes (nunca
omitidos) — convenção de `photovoltaic/serialization.py:1-7`.

**Taxonomia de indisponibilidade — os três motivos são mutuamente exclusivos e derivam do código
existente, sem cálculo novo:**

| Motivo | Condição | Evidência |
|---|---|---|
| `NOT_REPORTED` | Não há linha `DailyEnergy` do device no dia | `production_alert.py:877` (`production_by_device.get(device_id)` → `None`) |
| `NO_IRRADIATION_READING` | O device reportou, mas não há irradiação > 0 no dia | `production_alert.py:867` e `:880` — o rendimento só é calculado quando `irradiation is not None and irradiation > 0` |
| `INSUFFICIENT_DEVICE_HISTORY` | Reportou, há irradiação, mas a mediana própria não existe: menos de 5 dias históricos com produção **e** irradiação | `production_alert.py:957-961` filtra por `len(ratios) >= MINIMUM_RENDIMENTO_SAMPLE_DAYS` (`:101`, valor 5) |

**⚠ Armadilha obrigatória para quem implementar:** `yield_status` **não** pode ser derivado de
`DeviceYieldAssessment.dropped`. Esse campo é `False` tanto quando o inversor está bem quanto
quando não foi possível avaliar (`production_alert.py:501-509`). `UNKNOWN` deriva de
`relative_to_own_median is None`, e só disso. O próprio código já trata essa distinção como
condição de correção do alerta (`production_alert.py:291-297`: *"silence is not evidence that the
day was fine"*). Confundir os dois transforma "não sei" em "está tudo bem" — o pior erro possível
nesta tela.

**Por que `device_normal_threshold` vai no envelope:** para que o frontend nunca precise saber que
o limiar é 0,85. O projeto já tem uma violação desse tipo a corrigir —
`YIELD_ATYPICAL_THRESHOLD_PERCENT = 20` vive em `frontend/src/lib/dashboard/yield.ts:31` (T7 do
plano). Não criar a segunda.

**Por que `last_reported_date` entra** (única adição além da lista de aceite da T1): sem ela,
"não reportou hoje" e "está mudo há três semanas" são visualmente idênticos, e são fatos de
gravidade completamente diferentes. Custa uma coluna a mais numa query agrupada por device
(`max(production_date)`), sobre ~2 devices. É o campo mais barato de cortar se o usuário quiser
reduzir escopo.

**Fora do payload de propósito:** `dc_capacity_kwp` / `ac_capacity_kw` (já expostos por
`GET /plants/{plant_id}/technical-configuration`, `plants/router.py:220-228` — são configuração,
não estado) e `expected_daily_production_kwh` (Decisão 4).

### 4. O conflito da expectativa obrigatória e do `raise`: resolvido por não entrar nele

`gather_production_alert_metrics` (`alerts/production_alert.py:191-247`) tem dois traços
incompatíveis com um endpoint de leitura: exige `expected_daily_production_kwh: Decimal`
obrigatório (`:196`) e **levanta** `ProductionAlertDataNotFoundError` quando nenhum device da
usina reportou no dia (`:199-203`).

O segundo é o mais grave: o dia em que **todos** os inversores ficaram mudos é precisamente o dia
mais importante de mostrar, e é exatamente o dia em que essa função se recusa a devolver dado.

**Decisão: a leitura não chama `gather_production_alert_metrics`.** Ela chama
`gather_device_metrics` e `assess_devices` diretamente (Decisão 2), mais uma leitura da irradiação
do dia. Isso é possível porque — verificado lendo `:199-247` inteiro —
`expected_daily_production_kwh` **não participa de nenhuma query nem de nenhum cálculo** dentro
dessa função: ela apenas o copia para o dataclass (`:239`). Quem o consome é
`assess_production_alert` (`:268-274`) e `render_production_alert` (`:391-395`) — nenhum dos dois
no caminho de leitura.

Consequências diretas:

- **A assinatura e o comportamento do caminho de alerta não mudam.** Nada de tornar o parâmetro
  opcional, nada de trocar `raise` por retorno nulo, nada de mexer em `send_production_alert`
  (`:426-489`) ou em `_count_consecutive_alert_days` (`:516-541`), que depende do `raise` como
  condição de parada (`:534-535`).
- **O payload não tem expectativa de produção.** A visão por inversor compara cada inversor com a
  mediana dele mesmo (Restrição 2) — a expectativa da usina não é insumo dela. Quem quer
  "esperado vs. realizado" já tem `/energy/anomalies/latest` e `/photovoltaic/summary`.
- **`observation_date` é resolvido pelo backend**, com uma query nova mínima:
  `max(DailyEnergy.production_date)` sobre as linhas dos devices da usina. Não existe helper para
  isso hoje (`grep -rn "max(DailyEnergy.production_date)" src/mplacas/` → vazio), então é código
  novo — mas é resolução de data, não fórmula.
- **Sem nenhuma `DailyEnergy`:** 200 com `observation_date: null`,
  `observation_date_unavailable_reason: "NO_PRODUCTION_HISTORY"` e `devices[]` **ainda listando os
  inversores cadastrados**, com `reporting_status: "NOT_REPORTED"`. Restrição 1 vale também no
  extremo.

**Precedente que NÃO deve ser copiado:** `/energy/anomalies/latest` ainda devolve 404 quando não
há dado nenhum (`intelligence/router.py:339-340`, alimentado por
`intelligence/anomaly_service.py:97-98`). É exceção herdada à convenção do §2.2, não modelo a
seguir. O modelo a seguir é `/photovoltaic/summary` (`photovoltaic/router.py:112-122`).

### 5. Frontend: módulo Técnico, abaixo do diagnóstico

**Onde:** `frontend/src/pages/dashboard/TechnicalPage.tsx`, nova `<section>` entre
`TechnicalDiagnosticPanel` (`:208-210`) e `TechnicalPerformanceSection` (`:212`).

**Por quê Técnico e não outro módulo** — o argumento decisivo é de adjacência, não de taxonomia: a
página já exibe o agregado "Disponibilidade dos dados — reporte dos devices" (`:173-178`) e o
`ReportingAvailabilityCard` com a mesma fração. A lista por inversor é o **drill-down de um número
que já está nessa tela**. Colocar a resposta ao lado da pergunta é o ganho de UX inteiro desta
tarefa. Visão Geral responde "minha conta está ok"; Produção é série temporal; Financeiro é
dinheiro — em nenhum deles um equipamento nomeado tem função.

**Fetch:** segunda instância de `usePlantResource` dentro do próprio `TechnicalPage`, com
`fetchDeviceDailyStatus` em `lib/api.ts` e `parseDeviceDailyStatus` em
`lib/dashboard/device-contracts.ts`. Não compor com `/photovoltaic/summary`: ADR-072, Decisão 3
fixa a fronteira de fetch por módulo, e `usePlantResource` já isola falha por recurso
(`frontend/src/hooks/usePlantResource.ts:115-121` e `:202-209`). Uma falha do endpoint novo não
pode apagar PR, perdas e degradação da tela.

**Wireframe textual** (descrição, não implementação):

```
┌─ Inversores ──────────────────────────────── Leitura de 11/08/2026 ─┐
│                                                                     │
│  ┌───────────────────────────┐  ┌───────────────────────────┐       │
│  │ SN 1234567890             │  │ SN 0987654321             │       │
│  │ 12,5 kWh                  │  │ ⚠ Não reportou            │       │
│  │ Rendimento normal         │  │ Última leitura: 28/07      │       │
│  └───────────────────────────┘  └───────────────────────────┘       │
│                                                                     │
│  Cada inversor é comparado só com o histórico dele mesmo.           │
└─────────────────────────────────────────────────────────────────────┘
```

Regras de apresentação, todas derivadas das restrições:

1. **Ordem fixa por `serial_number`, a que o backend devolve.** Nenhuma ordenação por desempenho,
   nenhum destaque de "pior inversor", nenhuma comparação entre cards (Restrição 2).
2. **"Não reportou" nunca é `0` nem `—`.** É estado nomeado, com ícone + texto + cor
   (`--color-warning-text`), nunca cor sozinha. Um inversor que reportou `0,0 kWh` mostra
   `0,0 kWh` com tratamento visual **diferente**.
3. **Não exibir o rendimento bruto.** A unidade é kWh/(kWh/m²) — fisicamente uma área, sem
   significado para o usuário — e a página já mostra duas coisas chamadas "rendimento"
   (`SpecificYieldCard`, kWh/kWp, e `frontend/src/lib/dashboard/yield.ts`). Um terceiro número com
   o mesmo nome e outra unidade é convite à confusão. A tela mostra **só** o relativo:
   *"−28% em relação à mediana deste inversor"* — ou, quando o desvio arredonda para zero,
   *"Em linha com a mediana deste inversor."* (ver correção de rota abaixo; nunca "−0%"/"+0%").
4. **Cada motivo de indisponibilidade tem frase própria**, nunca um "—" genérico:
   `NO_IRRADIATION_READING` → "sem leitura de irradiação neste dia";
   `INSUFFICIENT_DEVICE_HISTORY` → "histórico insuficiente para comparar (mínimo 5 dias)";
   `NOT_REPORTED` → "não reportou neste dia".
5. **Nenhum cálculo no frontend.** `relative_to_own_median`, `relative_to_own_median_deviation_percent`,
   `yield_status` e o limiar vêm prontos; o parser converte e formata, nada mais (regra 0.3.3 do
   plano) — ver correção de rota abaixo para o desvio percentual, que nasceu calculado no cliente e
   foi movido para o backend.
6. **Rodapé fixo** com a frase de comparação, para que a ausência de ranking seja explicada, não
   apenas omitida.

**Vocabulário — decisão de honestidade:** o campo se chama `reporting_status`, não
`communication_status`, e a tela diz "não reportou", não "inversor offline". O backend observa
ausência de linha em `daily_energy`; ele **não sabe** distinguir inversor desligado, internet
caída, provider fora do ar e coleta que não rodou. O projeto já aplica exatamente essa disciplina
no agregado (`frontend/src/components/ReportingAvailabilityCard.tsx:8-11`: *"é disponibilidade de
REPORTE de dados… O rótulo diz 'de reporte' para não sugerir uptime de inversor"*). Afirmar
"offline" seria inventar causa sem evidência.

**Correção de rota (2026-08-12, revisão P1 independente de T1c — dois achados corrigidos aqui):**

- *Achado 1 — cálculo derivado no frontend.* A implementação original desta regra 5 tratou
  `(relative_to_own_median − 1) × 100` como "conversão de unidade" equivalente a
  `photovoltaic-contracts.ts::ratioToPercent` (`x × 100`, reescala pura) e implementou o desvio em
  `device-contracts.ts::relativeToMedianPercent`, no frontend. Isso estava errado: `ratioToPercent`
  nunca desloca o zero; `(x − 1) × 100` **subtrai uma constante de domínio** (o `1` que significa
  "na mediana"), o que é algebricamente idêntico à violação já registrada em
  `frontend/src/lib/dashboard/yield.ts:54` (`((yieldValue − periodYield) / periodYield) × 100`
  reduz à mesma forma `(r − 1) × 100`) — dívida que o plano já lista para mover ao backend (T7 /
  D11). Correção: o cálculo passou para `devices/metrics.py::assess_devices`, que agora expõe
  `relative_to_own_median_deviation_percent` pronto (mesma nulidade de `relative_to_own_median`,
  nunca inventado à parte). `relativeToMedianPercent` foi removida; o frontend só formata. Uma
  guarda estática equivalente a `no-client-computed-expected-production.test.ts` protege
  `device-contracts.ts` contra a reintrodução do cálculo.
- *Achado 2 — sinal decidido antes do arredondamento.* `DeviceStatusSection.tsx` decidia o sinal
  (`+`/`−`) a partir do valor bruto e só depois arredondava para exibir, produzindo `"−0%"` para
  desvios como `-0.4` e `"+0%"` para `+0.4` — exatamente a faixa mais comum de um inversor
  saudável (desvio quase nulo contra a própria mediana), então o caso normal chegava a mostrar
  "Rendimento normal" ao lado de "−0% em relação à mediana deste inversor". Correção: arredonda
  primeiro, decide o sinal a partir do valor já arredondado, e trata `rounded === 0` de forma
  explícita com a redação "Em linha com a mediana deste inversor." — nunca `"−0%"`/`"+0%"`.

### 6. Escopo de entrega: endpoint primeiro, UI depois — ⚠ CONFIRMAR

**Recomendação: duas tarefas separadas, com um ponto de parada entre elas.**

- **T1a — backend.** Movimento do cálculo (Decisão 2) + módulo `devices/` + endpoint + testes +
  revisão do `reviewer` (toca autorização/tenancy).
- **Ponto de parada.** Capturar a resposta real da usina de produção para alguns dias e olhar
  quais estados de fato ocorrem.
- **T1b — frontend.** Parser com os 3 testes obrigatórios (§2.2) + seção no `TechnicalPage`.

Motivos, em ordem de força:

1. **A parte difícil do payload é a taxonomia de indisponibilidade, e ela é verificável antes de
   desenhar.** É plausível que a usina real caia em `INSUFFICIENT_DEVICE_HISTORY` com frequência:
   a mediana exige 5 dias com produção **e** irradiação (`production_alert.py:957-961`), e a
   irradiação depende de coleta climática que pode falhar. Se o estado dominante for "sem base de
   comparação", a tela certa não é a do wireframe acima — e isso muda o design, não o texto.
2. **Regra 0.3.6 do plano: uma tarefa por commit/PR.** Movimento de código, módulo novo, parser e
   UI são diffs de natureza diferente.
3. **A revisão fica mais afiada.** O diff que o `reviewer` precisa examinar (RLS, `ReadPlant`,
   `set_principal_context`) é Python puro e pequeno; misturá-lo com TSX dilui a atenção no ponto
   de segurança.
4. **T1a tem valor mesmo se T1b atrasar:** o endpoint já torna a informação auditável e
   consumível fora do Telegram.

O custo é uma entrega intermediária que o usuário final não vê. Aceito.

### 7. Identidade do inversor na tela: `serial_number`, sem ordinal inventado — ⚠ CONFIRMAR

A tela identifica o inversor pelo `serial_number`, que já é a identidade usada no alerta
(`production_alert.py:646`) e já é exposta por HTTP (`plants/router.py:223`).

**Recusado: inventar "Inversor 1 / Inversor 2".** O ordinal só poderia vir da ordem alfabética por
serial; cadastrar um terceiro inversor pode reordenar tudo, e o usuário que aprendeu que "o
Inversor 2 é o problemático" passaria a ler outra coisa sob o mesmo rótulo. Um apelido estável
exigiria coluna nova em `devices` — mudança de modelo de dados, fora de escopo aqui.

**Confirmar com o usuário:** serial cru é um rótulo ruim para leitura humana. Se o usuário quiser
apelido editável ("Inversor da garagem"), isso é tarefa própria, com migration e `reviewer`.

### 8. O que este ADR deliberadamente não promete

Expor o inversor individualmente **desloca o produto**: de *"acompanhamento da minha conta de
luz"* para *"monitoramento de ativo"*. O ADR registra isso como consequência assumida, não como
efeito colateral.

A partir do momento em que o produto nomeia um equipamento, o usuário passa legitimamente a
esperar coisas que hoje não existem:

| Expectativa que a tela cria | Estado hoje | Decisão |
|---|---|---|
| Histórico daquele inversor (série por device) | Dado existe (`DailyEnergy` é por device), endpoint não | **Fora de escopo.** Endpoint de série novo; só depois de haver uso real da visão diária |
| Alerta específico daquele inversor | O alerta é por usina; o device aparece só como linha no texto (`production_alert.py:635-688`) | **Fora de escopo.** Depende da T3 (o conteúdo do alerta não é persistido hoje) |
| Ficha do equipamento (modelo, garantia, instalação) | `model_name` existe (`db/models.py:128`), garantia/instalação não | **Fora de escopo.** Exige modelo de dados novo |
| Apelido editável | Não existe | **Fora de escopo.** Exige migration (Decisão 7) |
| Histórico de manutenção / ordem de serviço | Não existe nada | **Fora de escopo.** É outro produto |

Se o usuário não quiser assumir esse reposicionamento, **este é o momento de não fazer a T1** —
depois de a tela existir, recuar é regressão de funcionalidade percebida.

## Consequências

### Positivas

- A falha mais grave de uma usina de 2 inversores — um deles mudo — deixa de ser invisível para
  quem não usa Telegram. É o único ganho que justifica a tarefa sozinho.
- O cálculo passa a ter **um** dono (`devices/metrics.py`) e continua tendo **uma** implementação;
  o caminho de alerta e o de leitura não podem divergir por construção.
- A T7 (mover o cálculo de rendimento do frontend para o backend) ganha destino natural: o módulo
  passa a existir e já carrega a mediana e o limiar.
- Nenhuma dependência nova nos dois lados; nenhuma migration; nenhuma mudança de schema.
- Nenhum comportamento do alerta muda — a superfície mais crítica do produto fica intocada.

### Negativas

- Um módulo backend a mais (4 arquivos + testes) para uma frota de ~2 equipamentos por usina.
  Justificado pela fronteira conceitual, não pelo volume de dado.
- `TechnicalPage` passa de 1 para 2 requisições ao entrar no módulo — contraria em parte o ganho
  da ADR-072, Decisão 3 (Visão Geral caiu de 5 para 2). Aceito: é o módulo mais barato do painel
  hoje (6,51 kB gzip, §1.4 do plano) e a requisição é pequena e paralela.
- O movimento da Decisão 2 mexe no arquivo mais sensível do backend
  (`alerts/production_alert.py`), ainda que sem alterar corpo de função. Mitigado por ser etapa
  isolada com 29 testes existentes como rede.
- O produto assume a expectativa de monitoramento de ativo descrita na Decisão 8 sem entregá-la
  por inteiro. O usuário vai pedir histórico por inversor — e a tabela da Decisão 8 é a resposta
  certa a esse pedido, não uma surpresa.
- Payload de um dia único: quem quiser saber "há quantos dias está assim" tem só
  `last_reported_date`, não uma série.

## Validação

Backend (T1a):

- Usina com 2 devices, um sem `DailyEnergy` no dia: a resposta lista **os dois**, e o mudo vem com
  `reporting_status: "NOT_REPORTED"` e `production_kwh: null`. Este é o teste que prova a
  Restrição 1 — se alguém trocar a consulta por um `JOIN` a partir de `DailyEnergy`, ele falha.
- Device que reportou exatamente `0` kWh: `reporting_status: "REPORTED"`, `production_kwh: "0"`,
  distinguível do caso acima em todos os campos.
- Sem observação climática no dia: todos os devices com `yield_status: "UNKNOWN"` e
  `yield_unavailable_reason: "NO_IRRADIATION_READING"` — nunca `NORMAL`.
- Device com 4 dias de histórico: `INSUFFICIENT_DEVICE_HISTORY`, `rendimento_median: null`.
  Com 5 dias: mediana presente. Fixa o limiar de `MINIMUM_RENDIMENTO_SAMPLE_DAYS`.
- Usina sem nenhuma linha de `daily_energy`: **200**, `observation_date: null`,
  `observation_date_unavailable_reason: "NO_PRODUCTION_HISTORY"`, devices listados. Prova que o
  `raise` de `gather_production_alert_metrics` não vazou para a leitura.
- Device com `dropped=False` **e** `relative_to_own_median=None` resulta em `UNKNOWN`, nunca
  `NORMAL`. Teste dedicado à armadilha da Decisão 3.
- Ordem da lista igual à de `serial_number`, verificada com serials inseridos fora de ordem.
- Principal de outra organização é barrado conforme `ReadPlant`, e o handler chama
  `set_principal_context` (mesmo padrão de teste de tenancy dos demais routers de leitura).
- `tests/test_production_alert.py` passa com **29 testes** e **apenas a linha de import alterada**
  após o movimento da Decisão 2.
- Gate §0.4 backend verde, sem regressão contra o baseline de 840 passed / 6 skipped.

Frontend (T1b):

- Parser com os 3 casos obrigatórios (§2.2): payload válido, campo indisponível, payload
  malformado.
- Teste de comportamento: "não reportou" e "0,0 kWh" produzem textos acessíveis diferentes.
- Teste que falha se algum cálculo for reintroduzido no cliente — o projeto já tem esse padrão em
  `frontend/src/lib/dashboard/no-client-computed-expected-production.test.ts`.
- Nenhuma classe crua de cor; severidade com cor + texto (+ ícone).
- Falha do endpoint novo não derruba PR/perdas/degradação na mesma página.
- Gate §0.4 frontend verde; delta de bundle do chunk `TechnicalPage` registrado.

## Reversibilidade

**Alta para o endpoint e para a UI.** Nada é persistido, nenhum schema muda: remover a rota e a
seção volta ao estado atual sem migração de dado. O único custo é de percepção (Decisão 8).

**Média para o movimento do cálculo (Decisão 2).** Reverter exige mover cinco símbolos e três
constantes de volta e desfazer os imports — mecânico, e o mesmo conjunto de 29 testes protege a
volta. Por isso o movimento é a **primeira** etapa e vai sozinho no commit: se algo der errado, o
que se reverte é um commit de movimentação pura, não uma feature inteira.

**Baixa para a decisão de posicionamento de produto.** Ver Decisão 8: retirar a visão por
inversor depois de publicada é regressão percebida, não simplificação.

## Riscos e o que fica fora de escopo

**Riscos:**

- *`INSUFFICIENT_DEVICE_HISTORY` dominante.* A mediana por device exige 5 dias com produção **e**
  irradiação (`production_alert.py:957-961`). Se a coleta climática for esparsa, a tela vira um
  mostruário de "sem base de comparação". É exatamente o que o ponto de parada da Decisão 6
  existe para descobrir antes de investir em UI.
- *Leitura de "offline" onde só há "não reportou".* Mitigado pelo vocabulário fixado na Decisão 5,
  mas depende de disciplina de copy em qualquer texto futuro.
- *Comparação entre inversores pela via do olho.* Dois cards lado a lado com números diferentes
  convidam o usuário a comparar, mesmo com o rodapé explicando que não se deve. Não há mitigação
  técnica completa; se virar problema real, validar com `solar-domain-specialist` (consultivo)
  antes de qualquer mudança.
- *Regressão silenciosa no alerta.* Endereçada pelo isolamento da etapa de movimento e pelos 29
  testes existentes.

**Fora de escopo, explicitamente:**

- Série histórica por inversor, alerta por inversor, ficha de equipamento, apelido editável e
  histórico de manutenção (Decisão 8).
- Capacidades por device no payload — já em `GET /plants/{plant_id}/technical-configuration`
  (`plants/router.py:220-228`).
- Qualquer ranking, ordenação por desempenho ou métrica comparativa entre inversores
  (Restrição 2).
- Paginação, virtualização, busca e filtro (Restrição 4).
- Mover `_plant_rendimento_median` / `_irradiation_median` para `devices/` — são de nível de usina
  e continuam em `alerts/`.
- Unificar os três `30` de janela espalhados pelo projeto (`alerts/production_alert.py:71`,
  `intelligence/anomaly_service.py:30`, `reports/daily_digest.py:40`) — dívida preexistente, não
  ampliada aqui.
- Alterar `gather_production_alert_metrics`, `assess_production_alert` ou qualquer comportamento
  do alerta (Decisão 4).
