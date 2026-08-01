# ADR-055 — Endpoint de localização da usina ativa a coleta climática

## Status

Aceito.

## Contexto

O ADR-019/ADR-020 entregaram o pipeline de coleta climática (Open-Meteo) e o motor de anomalias
(`intelligence/anomaly_engine.py`) já sabe distinguir `LOW_PRODUCTION_WITH_LOW_IRRADIATION` (nublado,
esperado) de `LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION` (produção baixa sem explicação
climática — sinal real de problema). O pipeline diário (`orchestration/daily_pipeline.py`) já chama
`collect_and_persist_daily_climate` a cada execução.

Na prática, nada disso roda: `collection_service.py` recusa a coleta com "plant geographic
coordinates are not configured" porque `plants.latitude`/`plants.longitude` (colunas nuláveis,
`Numeric(9,6)`) nunca são preenchidas para a usina real em produção. Uma varredura no repositório
inteiro confirmou que **não existe nenhum caminho de escrita** para essas duas colunas — nem router,
nem script, nem migration de dado. O motor de anomalias fica permanentemente cego a clima, sempre
caindo em `LOW_PRODUCTION_WITHOUT_CLIMATE_CONTEXT`, não por limitação do motor (nenhuma linha dele
precisou mudar), mas por ausência do dado de entrada.

Este ADR fecha essa lacuna com um endpoint, e não com um script ou uma migration de dado.

## Decisão

1. **Novo pacote `src/mplacas/plants/`**, com `router.py` expondo
   `PATCH /plants/{plant_id}/location`, corpo `{"latitude": Decimal, "longitude": Decimal}`.

2. **Coordenadas continuam por usina, não em configuração global.** `Plant.latitude`/`Plant.longitude`
   já existiam como colunas do modelo desde o ADR-019; este ADR não muda o schema, só cria o caminho
   de escrita. Um `MPLACAS_PLANT_LATITUDE`/`_LONGITUDE` global não escalaria para o objetivo já
   declarado no ADR-045/ADR-052 (organizações e, eventualmente, múltiplas usinas por organização) — a
   localização é intrinsecamente um atributo de usina, não de processo.

3. **Autorização via `core.tenancy`, reaproveitando o mecanismo do ADR-053/ADR-054, sem caminho
   paralelo.** O endpoint carrega `plant_id` no *path* (`/plants/{plant_id}/location`), não como query
   param — nenhum router existente tinha esse formato. `core.tenancy.resolve_admin_plant` resolve
   `plant_id` como `Query(default=None)`; declarar um path param de mesmo nome sob essa dependency
   colide (`AssertionError: Cannot use Query for path param 'plant_id'` — FastAPI não faz merge
   automático de path e query para o mesmo nome dentro de uma sub-dependency). A correção foi
   estender `core/tenancy.py` com `resolve_admin_plant_path` / `AdminPlantPath`, espelhando
   exatamente `resolve_admin_plant`/`AdminPlant` (mesmo `require_plant_access`, mesmo 404 em vez de
   403 para usina alheia), mudando apenas `Query(...)` por `Path(...)`. Nenhuma lógica de autorização
   nova: é a mesma função de resolução, parametrizada pela origem do valor. `tests/test_plant_scope_guard.py`
   reconhece `AdminPlantPath` estruturalmente (é `Annotated[ScopedPlant, Depends(...)]`, o mesmo
   formato que o guard já verifica), então a rota nova passa sem allowlist — confirmado rodando o
   teste, não assumido.

4. **Validação de faixa no modelo Pydantic** (`Field(ge=-90, le=90)` / `Field(ge=-180, le=180)`),
   espelhando os limites já aplicados defensivamente em
   `climate.collection_service.collect_and_persist_daily_climate`. Sem essa validação na borda HTTP,
   uma coordenada fora de faixa persistiria aqui só para ser rejeitada ali, de forma opaca, na próxima
   execução do pipeline diário.

5. **Auditoria via `AuditEventRepository`**, ação `plant.location_updated`, `resource_type="plant"`,
   `resource_id=plant_id`, mesmo padrão de `organizations/router.py` e `climate/router.py`. `details`
   carrega só latitude/longitude enviadas — nenhum dado de credencial ou payload externo.

6. **Endpoint, não script one-off.** Um script (`scripts/set-plant-location.py`, por exemplo) exigiria
   acesso direto ao ambiente de produção para cada usina nova, não deixaria rastro de auditoria
   estruturado e não se integraria ao fluxo de onboarding self-service que o ADR-054 já estabeleceu
   para organizações. O endpoint é reutilizável por toda organização nova sem intervenção manual, e
   fica sujeito à mesma auditoria que qualquer outra mutação administrativa do sistema.

## Consequências

### Positivas

- **Existe, pela primeira vez, um caminho de escrita para `plants.latitude`/`plants.longitude`.**
  Sem ele, a coleta climática nunca poderia rodar com sucesso em produção, independentemente de
  quanto o pipeline ou o motor de anomalias evoluíssem.
- **O motor de anomalias deixa de ser estruturalmente cego a clima** assim que um ADMIN configura a
  usina: `LOW_PRODUCTION_WITHOUT_CLIMATE_CONTEXT` passa a poder se resolver em
  `LOW_PRODUCTION_WITH_LOW_IRRADIATION` ou `LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION`, sem
  nenhuma mudança no motor em si.
- **`core.tenancy` ganha um segundo formato de resolução de `plant_id` (path, além de query) sem
  duplicar a lógica de autorização** — `resolve_admin_plant_path` é a mesma validação de escopo,
  parametrizada pela fonte do valor. Fica disponível para qualquer router futuro que precise de
  `plant_id` no path.
- **Auditável e testável de ponta a ponta**: releitura do banco confirma persistência real, não só o
  código de resposta HTTP; a tentativa cross-tenant é verificada por 404 e por releitura mostrando a
  usina intocada.

### Negativas

- **Nenhuma validação geográfica além da faixa numérica.** Um ADMIN pode configurar coordenadas
  matematicamente válidas mas fisicamente erradas (usina em outro continente); o sistema não tem como
  detectar isso sozinho — é o mesmo nível de confiança já depositado em outros campos administrativos
  (ex: `installed_power_kwp`). Aceito conscientemente: validar contra um serviço de geocodificação
  externo adicionaria uma dependência de rede a um endpoint administrativo de baixa frequência, por um
  benefício marginal.
- **Não há endpoint de leitura dedicado.** A resposta do `PATCH` devolve a localização atual, mas não
  existe `GET /plants/{plant_id}/location` para conferir o valor sem alterá-lo. Aceito porque o caso de
  uso imediato é "configurar uma vez, no onboarding"; se a necessidade de leitura isolada aparecer,
  adicionar o `GET` é aditivo e não exige mudar o `PATCH`.
- **Coordenadas ficam sujeitas a sobrescrita silenciosa por qualquer ADMIN da organização**, sem
  histórico de versões anteriores (a auditoria registra o valor novo em `details`, não guarda um diff
  explícito do valor antigo — embora o registro anterior continue reconstituível varrendo os eventos
  `plant.location_updated` em ordem, já que cada um carrega o valor efetivamente aplicado).

## Validação

- `tests/test_plants_router.py`: ADMIN da própria organização atualiza com sucesso (releitura do
  banco confirma persistência), ADMIN de outra organização recebe 404 e a usina alvo permanece
  intocada (releitura confirma), latitude/longitude fora de faixa rejeitadas com 422 (4 casos
  parametrizados), papel READ recebe 403, evento de auditoria `plant.location_updated` confirmado por
  releitura da tabela de auditoria.
- `tests/test_plant_scope_guard.py`: `/plants` adicionado a `_DATA_PREFIXES`; a rota nova passa
  estruturalmente via `AdminPlantPath` (`Annotated[ScopedPlant, ...]`), sem precisar de allowlist —
  confirmado rodando o teste, não assumido.
- `ruff check .`, `mypy`, `pytest -q` completos, verde (exceto os 3 testes de contrato de infraestrutura
  pré-existentes e não relacionados: `test_container_contract.py`,
  `test_gcp_deployment_contract.py`).

## Reversibilidade

O ponto de reversão é o próprio router: remover `plants/router.py` e o `include_router` correspondente
em `main.py` volta ao estado anterior (colunas nuláveis sem caminho de escrita), sem exigir rollback de
schema — nenhuma migration nova foi criada, `Plant.latitude`/`Plant.longitude` já existiam desde o
ADR-019. `AdminPlantPath`/`resolve_admin_plant_path`, em `core/tenancy.py`, podem permanecer mesmo se o
router for removido: são infraestrutura genérica, não acoplada a este endpoint específico.

## Referências

- ADR-019: pipeline de coleta climática — origem das colunas `Plant.latitude`/`Plant.longitude` e das
  faixas de validação (`-90..90`/`-180..180`) espelhadas aqui na borda HTTP.
- ADR-020: adaptador operacional Open-Meteo.
- ADR-013: motor de anomalia climática — o consumidor final do dado que este ADR desbloqueia.
- ADR-053: isolamento por organização aplicado nos routers — origem de `core.tenancy.AdminPlant`/
  `resolve_admin_plant`, estendido aqui com a variante `AdminPlantPath` para `plant_id` no path.
- ADR-054: onboarding de organizações — o mesmo princípio de "endpoint reutilizável e auditável em vez
  de script/intervenção manual" aplicado aqui à configuração de localização.
