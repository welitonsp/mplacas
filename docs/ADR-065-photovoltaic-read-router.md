# ADR-065 — Router HTTP de leitura para a modelagem fotovoltaica

## Status

Aceito — 2026-08-03.

## Contexto

Os ADRs 057 a 063 introduziram uma cadeia completa de modelagem técnica fotovoltaica,
já calculada, versionada e persistida:

- `daily_solar_model_results` — POA modelado e correção térmica (ver ADR-058).
- `daily_pv_performance_results` — performance ratio estilo IEC 61724, yield específico
  em kWh/kWp e disponibilidade de reporte (ver ADR-059).
- `seasonal_pv_baseline_results` — baseline sazonal robusto e degradação (ver ADR-060).
- `daily_pv_loss_assessments` — taxonomia de perdas com nível de evidência (ver ADR-061).

O cálculo já roda em produção: `orchestration/daily_pipeline.py:107-139` invoca
`calculate_and_persist_daily_performance`, `calculate_and_persist_seasonal_baseline` e
`classify_and_persist_daily_losses` no pipeline diário.

A auditoria de UI encontrou o gap: **não existe nenhuma rota HTTP que exponha esses
dados**. `main.py:147-161` registra 15 routers e nenhum pertence ao módulo
`photovoltaic/` — o pacote sequer tem um `router.py`. O produto calcula PR corrigido por
temperatura, degradação anualizada e atribuição de causa de perdas, e não mostra nada
disso. É o maior desvio entre o que o sistema sabe e o que o usuário vê.

Este ADR decide **apenas a superfície de leitura**. Não altera nenhum modelo de dados,
nenhum cálculo e nenhuma migration.

Uma dificuldade específica motivou boa parte do desenho. `SeasonalPvBaselineRecord` só
existe quando o baseline é defensável: `calculate_seasonal_baseline`
(`seasonal_baseline.py:65-168`) levanta `InsufficientBaselineData` em seis situações
distintas — sem observações elegíveis, ano de referência congelado incompleto, amostras
sazonais insuficientes, envelope de céu limpo indisponível, amostras robustas
insuficientes após o filtro MAD, e amostras de comparação insuficientes. O service
captura a exceção e devolve `skip_reason` numa dataclass em memória
(`seasonal_baseline_service.py:92-93`), que **não é persistida em lugar nenhum**. Do
ponto de vista do banco, "nunca foi calculado" e "foi calculado e é insuficiente" são
indistinguíveis. A API precisa dizer algo honesto para o caso "a usina é nova demais
para ter baseline", que é o estado normal do primeiro ano de qualquer usina.

## Decisão

### 1. Criar `src/mplacas/photovoltaic/router.py`, somente leitura

`APIRouter(prefix="/photovoltaic", tags=["photovoltaic"])`, sem prefixo de versão —
consistente com todos os routers existentes (`/climate`, `/energy`, `/reports`).
Registrado em `main.py` junto aos demais.

Nenhuma rota de escrita ou de recálculo. O cálculo continua sendo responsabilidade
exclusiva do pipeline diário (ver ADR-046); a API só lê o que ele persistiu.

### 2. Autenticação, autorização e isolamento por tenant

Todas as rotas usam a dependência `ReadPlant` de `core/tenancy.py:228`, exatamente como
`intelligence/router.py:161` e `reports/router.py:84`. Consequências herdadas, sem
código novo de autorização:

- `plant_id` é query param obrigatório;
- `principal.require_plant_access(plant_id)` roda antes do handler
  (`core/tenancy.py:117`), devolvendo **404, não 403**, para usina fora do escopo, para
  não revelar a existência de usina de outro tenant (ver ADR-053);
- cada handler abre `async with SessionFactory() as session` e chama
  `await set_principal_context(session, scoped.principal)` **antes de qualquer query**,
  ativando as GUCs `mplacas.organization_id` e `mplacas.platform_bypass` que as políticas
  de RLS consomem (`db/tenant_context.py:113-129`).

As quatro tabelas fotovoltaicas já estão sob RLS `ENABLE` + `FORCE` como `PLANT_TABLES`
em `migrations/versions/20260802_0040_enable_postgresql_rls.py:32-46` (ver ADR-056,
PostgreSQL Row Level Security). O router novo, portanto, **não amplia a superfície de
tabelas expostas sem RLS**; ele só adiciona um caminho de leitura sobre tabelas já
protegidas. É defesa em profundidade: escopo de usina no dependency e RLS no banco.

### 3. Serialização

Segue o padrão de `intelligence/router.py:31-67`: dicionários simples, sem
`response_model` Pydantic, **`Decimal` serializado como string** (`str(valor)`) para não
perder precisão nem casas decimais significativas, datas em ISO-8601.

Unidades: `daily_pv_performance_results.units_json` já carrega o dicionário
`PERFORMANCE_UNITS` (`performance.py:20-28`, persistido em
`performance_service.py:134`). A resposta **ecoa `units_json` do próprio registro**, não
uma constante importada — assim um registro antigo continua descrevendo as unidades com
que foi gravado. `seasonal_pv_baseline_results` e `daily_pv_loss_assessments` não têm
`units_json`; para eles o router expõe um bloco `units` estático definido no módulo.

Os campos `limitation`, `quality_flags`, `evidence_codes`, `performance_ratio_nature`,
`availability_nature` e `uncertainty_nature` são **sempre incluídos, nunca omitidos**.
São a parte do contrato que impede a UI de apresentar um proxy como medição: o
`estimated_loss_percent` de COMMUNICATION, por exemplo, é capacidade de reporte ausente,
não energia perdida confirmada (`loss_taxonomy.py:139`).

### 4. Rotas

**`GET /photovoltaic/performance/latest?plant_id=`**
Registro mais recente de `DailyPvPerformanceRecord` filtrado por
`performance_model_version == PERFORMANCE_MODEL_VERSION` e
`solar_model_version == poa.MODEL_VERSION`. Esse par de filtros torna o resultado único
por dia pela unique constraint `uq_daily_pv_performance_identity` (`db_models.py:87-93`),
eliminando a ambiguidade que o service de perdas trata em
`loss_taxonomy_service.py:58-61`. Ordena por `observation_date DESC`, limite 1.
**404** com `detail="no photovoltaic performance result for this plant"` quando não há
registro — consistente com `/energy/trends/latest` e `/reports/monthly/latest`.

Campos: `observation_date`, `measured_energy_kwh`, `dc_capacity_kwp`,
`poa_irradiation_kwh_m2`, `final_yield_kwh_per_kwp`, `reference_yield_hours`,
`performance_ratio`, `temperature_corrected_performance_ratio` (nullable — só existe se
o POA térmico foi modelado, `performance.py:95-104`), `reporting_availability_ratio`
(nullable — null quando alguma capacidade DC de device é desconhecida,
`performance.py:131-132`), `reporting_device_count`, `configured_device_count`,
`reporting_capacity_kwp` (nullable), `configured_device_capacity_kwp` (nullable),
`data_quality_status` (`FINAL`, `PROVISIONAL` ou `INCOMPLETE`), `quality_flags`,
`uncertainty_percent` (nullable — hoje sempre null, `performance_service.py:116`),
os três campos `*_nature`, `climate_source`, `solar_model_version`,
`performance_model_version`, `units`, `calculated_at`.

**`GET /photovoltaic/performance?plant_id=&start_date=&end_date=`**
Série diária para gráfico de PR e yield. Mesmos filtros de versão, ordenada por
`observation_date ASC`. **200 com `items: []`** quando não há dados no intervalo — lista
vazia não é erro. **422** quando `end_date < start_date` ou quando a janela excede 366
dias, espelhando `REFERENCE_WINDOW_DAYS` (`seasonal_baseline.py:13`) para que a UI
consiga plotar um ano de referência inteiro e nada além disso. O 422 para rejeição de
domínio segue `climate/router.py:82`.
Envelope: `{plant_id, start_date, end_date, count, units, items: [...]}`.

**`GET /photovoltaic/baseline/latest?plant_id=`**
Registro mais recente de `SeasonalPvBaselineRecord` com
`baseline_model_version == BASELINE_MODEL_VERSION`. Campos: `observation_date`,
`season_key`, `reference_start_date`, `reference_end_date`, `baseline_sample_count`,
`baseline_excluded_count`, `comparison_start_date`, `comparison_sample_count`,
`clear_sky_poa_p90_kwh_m2`, `target_clear_sky_index` (nullable),
`baseline_median_performance_ratio`, `baseline_mad`, `baseline_q10`, `baseline_q90`,
`comparison_median_performance_ratio`, `degradation_percent`,
`annualized_degradation_percent` (nullable — só existe com no mínimo 180 dias de
separação entre os midpoints, `seasonal_baseline.py:129`), `degradation_status`
(`STABLE`, `WATCH` ou `DEGRADED`), `metric_nature`, `clear_sky_index_nature`,
`quality_flags`, `assumptions`, `units`, `calculated_at`.
**404** quando não há registro, com o código de motivo da seção 6 embutido no `detail`.

**`GET /photovoltaic/losses/latest?plant_id=`**
As oito categorias de `DailyPvLossAssessmentRecord` da data mais recente que possui
avaliações, filtradas por `taxonomy_model_version == LOSS_TAXONOMY_MODEL_VERSION` (a
unique constraint `uq_daily_pv_loss_assessment_identity` garante no máximo uma linha por
categoria). Ordem de retorno fixa e igual à de `classify_daily_losses`
(`loss_taxonomy.py:110-119`): COMMUNICATION, UNAVAILABILITY, CLIPPING, SOILING, SHADING,
TEMPERATURE, DEGRADATION, UNEXPLAINED — a UI não deve reordenar por severidade, porque
`NOT_ASSESSABLE` não é menos importante que `NOT_DETECTED`, é uma afirmação diferente.
Cada item: `category`, `evidence_level`
(`LIKELY`, `POSSIBLE`, `NOT_DETECTED` ou `NOT_ASSESSABLE`), `estimated_loss_percent`
(nullable, unidade `percent`), `evidence_codes`, `limitation` (nullable),
`taxonomy_model_version`, `baseline_model_version` (nullable).
Envelope: `{plant_id, observation_date, units, items: [...]}`. **404** quando não há
nenhuma avaliação.

**`GET /photovoltaic/summary?plant_id=`**
Composição das três leituras acima para o dashboard, em **uma única requisição e uma
única sessão**. Sempre **200** quando o chamador tem acesso à usina; cada bloco é
nullable e acompanhado de um código de motivo:

```json
{
  "plant_id": "...",
  "performance": null,
  "performance_unavailable_reason": "NO_PERFORMANCE_RESULTS",
  "baseline": null,
  "baseline_unavailable_reason": "REFERENCE_YEAR_INCOMPLETE",
  "reference_complete_on": "2027-03-14",
  "losses": null,
  "losses_unavailable_reason": "NO_LOSS_ASSESSMENTS"
}
```

### 5. Regra de status: 404 nos recursos, 200 no resumo

A regra é explícita e não se decide caso a caso:

- rota que representa **um recurso** (`/performance/latest`, `/baseline/latest`,
  `/losses/latest`) devolve **404** quando o recurso não existe;
- rota que representa **uma coleção** (`/performance`) devolve **200 com lista vazia**;
- rota que representa **um agregado de dashboard** (`/summary`) devolve **200** com
  blocos nulos e motivo, porque um dashboard cujo card de degradação ainda não existe
  não é uma requisição malsucedida.

Isso mantém as rotas `/…/latest` alinhadas a `intelligence/router.py:194` e
`explanations/router.py:59`, e evita que a UI precise tratar quatro 404 encadeados no
carregamento inicial de uma usina nova.

### 6. Como comunicar "dado insuficiente" sem alterar o modelo de dados

O motivo de indisponibilidade do baseline é **derivado por consulta agregada** sobre
`daily_pv_performance_results`, aplicando em SQL a parte de
`seasonal_baseline._eligible` (`seasonal_baseline.py:171-180`) que é expressável em SQL:
`performance_model_version = PERFORMANCE_MODEL_VERSION AND data_quality_status = 'FINAL'
AND reporting_availability_ratio >= 0.95`. Sobre `MIN(observation_date)` e `COUNT(*)`
dessas linhas:

1. `COUNT(*) = 0` produz **`NO_PERFORMANCE_HISTORY`**;
2. `MIN(observation_date) + 365 dias >= hoje` produz **`REFERENCE_YEAR_INCOMPLETE`**,
   acompanhado do campo `reference_complete_on` (data ISO) para a UI dizer "disponível a
   partir de <data>";
3. qualquer outro caso produz **`INSUFFICIENT_SEASONAL_SAMPLES`**.

`INSUFFICIENT_SEASONAL_SAMPLES` é assumidamente um **código guarda-chuva**: cobre os
quatro motivos restantes de `InsufficientBaselineData` (amostras sazonais, envelope de
céu limpo, amostras robustas pós-MAD, amostras de comparação) sem distinguir entre eles.
A distinção exata exigiria persistir o `skip_reason` — ver "Alternativas descartadas".

### 7. Fora de escopo, deliberadamente

- Endpoint para `daily_solar_model_results` (GHI, componente direta, difusa, temperatura
  de célula). O `poa_irradiation_kwh_m2` relevante já está desnormalizado no registro de
  performance, e a UI ainda não tem tela para decomposição de irradiância.
- Histórico de perdas em série temporal. Só faz sentido depois que a tela de perdas do
  dia existir e provar seu valor.
- Qualquer rota de escrita ou de recálculo sob demanda.

## Consequências

### Positivas

- Fecha o maior gap de produto identificado na auditoria de UI: a superfície de leitura
  passa a cobrir toda a modelagem dos ADRs 057-063.
- Zero mudança de modelo de dados, zero migration, zero alteração de cálculo. É um ADR de
  superfície, com risco de regressão confinado ao arquivo novo.
- O contrato preserva as ressalvas epistêmicas do domínio: `evidence_level`,
  `limitation`, os campos `*_nature` e `quality_flags` viajam sempre, então a UI não
  consegue acidentalmente apresentar disponibilidade de reporte como disponibilidade
  técnica, nem risco de clipping como clipping confirmado.
- Usina nova deixa de ser um erro: `/summary` explica por que ainda não há baseline e
  quando haverá.

### Negativas

- **Mais um router para manter.** Quinze passam a dezesseis. Cada mudança futura de
  convenção de auth ou de tenancy ganha mais um ponto de aplicação.
- **Mais superfície de auth e RLS.** Ainda que o padrão seja idêntico ao existente e as
  tabelas já estejam sob RLS, um `set_principal_context` esquecido em um handler abriria
  vazamento entre tenants. Mitigação: teste de fronteira obrigatório, no molde de
  `tests/test_climate_tenant_boundaries.py`, cobrindo **cada uma das cinco rotas**.
- **O código `INSUFFICIENT_SEASONAL_SAMPLES` é menos preciso do que o motor sabe ser.**
  A API dirá "amostras sazonais insuficientes" onde internamente o motivo pode ter sido o
  filtro MAD ou o envelope de céu limpo. É imprecisão consciente, em troca de não mexer
  em schema.
- **Duplicação da lógica de elegibilidade.** O predicado da seção 6 reimplementa em SQL
  parte de `_eligible`. Se `_eligible` mudar, o código de motivo diverge silenciosamente.
  Mitigação: teste que fixa a correspondência entre os dois, com comentário cruzado nos
  dois arquivos apontando um para o outro.
- **Sem `response_model` Pydantic**, não há schema OpenAPI rico para essas rotas. Aceito
  por consistência com os 15 routers existentes; introduzir Pydantic só aqui criaria um
  segundo padrão de serialização no projeto.
- **`/summary` executa de três a cinco queries por requisição** e não tem cache. Aceito:
  são leituras indexadas por `plant_id` com `LIMIT`, e o volume de dashboard é baixo. Se
  virar problema, o caminho é um read model como `intelligence/dashboard_readmodel.py`
  (ver ADR-049), não cache no router.

## Validação

1. Testes de contrato por rota em `tests/test_photovoltaic_router.py`: forma da resposta,
   `Decimal` como string, campos nullable presentes com valor `null` (nunca ausentes),
   `units` ecoado de `units_json`.
2. Teste de que a ordem das oito categorias de perda é idêntica à de
   `classify_daily_losses`.
3. Teste de que `limitation` e `evidence_codes` sobrevivem à serialização em todas as
   categorias, inclusive as `NOT_ASSESSABLE`.
4. Testes dos três códigos de indisponibilidade de baseline, incluindo
   `reference_complete_on` no caso `REFERENCE_YEAR_INCOMPLETE`.
5. Teste de fronteira de tenant nas cinco rotas: principal da organização A recebe **404**
   ao pedir `plant_id` da organização B.
6. Teste de que `/summary` devolve 200 com todos os blocos nulos para uma usina sem
   nenhum dado fotovoltaico.
7. Teste de janela: `/photovoltaic/performance` devolve 422 para janela invertida e para
   janela maior que 366 dias.
8. CI verde: ruff, mypy, pytest.

## Alternativas descartadas

- **Persistir o `skip_reason` do baseline** (coluna nova ou tabela de tentativas). Daria
  o motivo exato em vez do guarda-chuva. Descartado neste ADR por ser mudança de modelo
  de dados com migration, fora do escopo de "expor o que já existe" — mas é o caminho
  natural se a imprecisão incomodar na prática, e exige decisão explícita do usuário.
- **Recalcular `calculate_seasonal_baseline` no caminho de leitura** para capturar
  `InsufficientBaselineData` e devolver a mensagem exata. Descartado: colocaria uma
  varredura de até 366 dias de linhas mais um cálculo estatístico completo em cada
  carregamento de dashboard, para produzir uma string.
- **200 com `data: null` em todas as rotas, inclusive as `/latest`.** Seria internamente
  mais uniforme, mas divergiria de `/energy/trends/latest`, `/energy/executive/latest`,
  `/energy/explanations/latest` e `/reports/monthly/latest`, que já usam 404.
  Consistência com o que existe venceu consistência interna do módulo novo.
- **Rotas aninhadas em `/plants/{plant_id}/photovoltaic/...`.** Mais RESTful, mas o
  projeto padronizou `plant_id` como query param via `ReadPlant`; um segundo padrão de
  escopo é exatamente o tipo de divergência que gera falha de isolamento (ver ADR-053).

## Reversibilidade

Alta. A decisão adiciona um arquivo e uma linha em `main.py`. Remover
`app.include_router(photovoltaic_router)` retira toda a superfície sem tocar em dados,
migrations ou cálculo. O ponto de extensão para o caminho descartado do `skip_reason`
persistido é `seasonal_baseline_service.py:92-93`, onde o motivo já existe em memória e
hoje é descartado.
