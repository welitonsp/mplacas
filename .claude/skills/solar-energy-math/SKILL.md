---
name: solar-energy-math
description: Use SEMPRE que uma tarefa envolver cálculo numérico de energia solar no Mplacas — reconciliação produção/injeção/consumo, performance vs esperado, anomalia de yield ou climática, conversão de irradiância, ou parsing de valores numéricos de fatura. Evita duplicar fórmula já existente em outro módulo, mantém convenção de unidades e cobre os edge cases numéricos que o domínio exige.
---

# Cálculo de energia solar — Mplacas

## Onde cada fórmula já vive (não crie uma sexta versão)

| Cálculo | Arquivo:linha | Fórmula |
|---|---|---|
| Reconciliação 3 vias (produção/injeção/consumo) | `src/mplacas/billing/models.py:59` `reconcile_bill()` | `self_consumption = max(0, produção − injetado)`; `total_consumption = importado + self_consumption` |
| Reconciliação 3 fontes (com medidor da concessionária) | mesmo arquivo, mesmo método | `meter_vs_injection = medidor_gerador − injetado`; `origin_vs_meter = produção_NEPViewer − medidor` |
| Performance vs esperado + health score | `src/mplacas/intelligence/energy_engine.py:114` `analyze_energy_cycle()` | `performance% = produção/esperado*100` (faixas: <70% CRITICAL, <85% WARNING); `credit_coverage% = compensado/importado*100` |
| Anomalia diária com contexto climático | `src/mplacas/intelligence/anomaly_engine.py:52` `assess_daily_performance()` | `deviation% = (real−esperado)/esperado*100` (faixas: 15/30/50%); cruza com irradiância `< 2.0 kWh/m²` antes de atribuir causa |
| Yield específico (anomalia simples) | `src/mplacas/anomalies/engine.py:46` `detect_daily_yield()` | `specific_yield = energy_kwh / installed_power_kwp` (threshold fixo `0.50 kWh/kWp`) |
| Completude de produção no ciclo | `src/mplacas/billing/production.py:30` `summarize_cycle_production()` | soma diária com detecção de dias faltantes/provisórios/duplicados |
| Conversão de irradiância | `src/mplacas/climate/open_meteo.py:104` | `kWh/m² = shortwave_radiation_sum (MJ/m²) / 3.6` |
| Parsing decimal BR de fatura | `src/mplacas/billing/parser.py:198` `_parse_decimal()` | `"1.234,56"` → `1234.56` via regex |

Antes de escrever uma fórmula nova, **grep pelo nome do cálculo** — se já existe algo
parecido em outro módulo, a decisão de criar uma variante (vs reusar/generalizar) é do
`architect`, não uma escolha implícita do worker.

## Convenção de unidades — não misture

- `kWh` — energia (produção, injeção, consumo, compensação).
- `kWp` — potência instalada (nameplate do sistema).
- `kWh/kWp` — yield específico (energia normalizada pela potência instalada).
- `kWh/m²` — irradiância acumulada no período (não confundir com `MJ/m²`, a unidade
  bruta que vem do Open-Meteo — sempre converter antes de comparar com outro dado de
  irradiância).
- `%` — todos os percentuais do projeto (`performance%`, `deviation%`,
  `self_consumption_rate%`, `credit_coverage%`) são proporções multiplicadas por 100,
  não frações — confira o sinal antes de propagar um valor para relatório/alerta.

Não introduza uma nova unidade (ex: Wh, MWh) num módulo que já opera em kWh sem
converter explicitamente e documentar a conversão inline.

## Thresholds hardcoded existentes (mantenha em sync se mudar um)

- Performance: `<70%` CRITICAL, `<85%` WARNING (`energy_engine.py`).
- Desvio de anomalia: `15% / 30% / 50%` (ATTENTION/ANOMALY/CRITICAL, `anomaly_engine.py`).
- Baixa irradiância: `< 2.0 kWh/m²` (`anomaly_engine.py`).
- Yield específico mínimo: `0.50 kWh/kWp` (`anomalies/engine.py`).

Esses quatro conjuntos de threshold são independentes e **não estão centralizados** —
se o usuário pedir para "ajustar a sensibilidade de detecção de anomalia", confirme
qual dos dois motores de anomalia (`intelligence/anomaly_engine.py` vs
`anomalies/engine.py`) ele quer dizer; são módulos distintos com critérios distintos,
apesar do nome parecido.

## O que ainda NÃO existe no projeto (não assuma que existe)

- Performance ratio (PR) formal — `energia real / (irradiância × área × eficiência)`.
  O que existe é `performance%` (real/esperado), que é uma proxy diferente.
- Modelagem de clipping do inversor.
- Degradação anual de painel.
- Valorização monetária do crédito de energia (net metering em R$) — `credit_coverage%`
  hoje é só proporção em kWh, sem preço.

Se a tarefa pedir um desses, é fórmula nova — trate como decisão de arquitetura
(`architect`), não como extensão trivial de um cálculo existente.

## Edge cases numéricos obrigatórios em teste

Ao escrever ou alterar qualquer um desses cálculos, o teste **MUST** cobrir:

- `installed_power_kwp = 0` ao calcular yield específico — divisão por zero.
- `produção < injetado` (self_consumption negativo antes do `max(0, ...)`).
- `generation_cycle_kwh` ausente (`None`) — a reconciliação de 3 fontes deve degradar
  para 2 fontes sem quebrar, não estimar o valor ausente.
- Dia com irradiância zero ou ausente — não atribuir causa climática sem evidência
  (ver o cruzamento já existente em `anomaly_engine.py`).
- `esperado = 0` no cálculo de `performance%`/`deviation%` — mesma classe de bug que
  `installed_power_kwp = 0`.
- Decimal malformado no parsing BR (`_parse_decimal`) — string vazia, sem vírgula, com
  múltiplos separadores.
- Dias faltantes/provisórios/duplicados no somatório de ciclo (já parcialmente coberto
  em `test_billing_cycle_production.py` — siga o mesmo padrão para módulo novo).

## Cobertura hoje abaixo do padrão do projeto (atenção redobrada ao tocar)

- `src/mplacas/anomalies/engine.py` — só 2 casos em `tests/test_anomaly_engine.py`.
  Ao alterar esse arquivo, expanda a cobertura antes de considerar a tarefa concluída,
  não apenas ajuste o caso que motivou a mudança.
- Conversão de irradiância em `climate/open_meteo.py:104` — sem teste numérico
  dedicado. Se tocar nessa linha, adicione um teste de conversão MJ/m² → kWh/m² com
  valor conhecido.
