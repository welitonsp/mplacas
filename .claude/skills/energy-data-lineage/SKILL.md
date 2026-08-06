---
name: energy-data-lineage
description: Use ao rastrear de onde um valor energético exibido na UI do Mplacas realmente vem — telemetria do provedor (NEPViewer) → clima (Open-Meteo) → POA → performance diária → baseline sazonal → taxonomia de perdas. Necessário para não misturar estágios do pipeline na apresentação.
---

# Energy Data Lineage — Mplacas

## Finalidade
Dar visibilidade da cadeia real de cálculo por trás de cada indicador, para debug e para não apresentar um dado de um estágio como se fosse de outro.

## Cadeia real (ordem sequencial, um pipeline diário)
1. **Telemetria bruta** do provedor (NEPViewer) — energia medida, dispositivos.
2. **Clima** (Open-Meteo) — irradiância, temperatura ambiente.
3. **POA** (`daily_solar_model_results`) — irradiância modelada no plano do array, depende da configuração técnica da usina (inclinação, azimute) estar preenchida.
4. **Performance diária** (`daily_pv_performance_results`) — PR, yield, disponibilidade — depende do POA do mesmo dia.
5. **Baseline sazonal** (`seasonal_pv_baseline_results`) — "o normal" da usina, exige 366 dias de referência acumulados a partir do primeiro dia elegível.
6. **Taxonomia de perdas** (`daily_pv_loss_assessments`) — depende da performance diária; algumas categorias (DEGRADATION, UNEXPLAINED) também dependem do baseline.

## Quando usar
- Ao investigar por que um card mostra "indisponível" — identifique em qual elo da cadeia a informação parou.
- Ao propor uma mudança que consome dado de um estágio — confirme que esse estágio realmente já roda antes do ponto onde o dado é necessário.

## Procedimento
1. Se um card depende de baseline mas a usina não tem 366 dias de histórico, o motivo é `REFERENCE_YEAR_INCOMPLETE` — não é bug, é o estágio 5 ainda não ter dado suficiente. Não trate como erro a corrigir no frontend.
2. Se a usina tem telemetria e clima mas nenhum resultado de performance, suspeite de configuração técnica ausente (estágio 3, inclinação/azimute/tecnologia do painel não preenchidos) — verifique `GET /plants/{id}/technical-configuration` antes de assumir bug de pipeline.
3. Nunca componha um valor de dois estágios diferentes manualmente no frontend — cada estágio já expõe seu resultado pronto via API.

## Anti-patterns
- Tratar `REFERENCE_YEAR_INCOMPLETE` como bug.
- Assumir que "sem performance" é falha de pipeline sem checar configuração técnica primeiro.

## Checklist
- [ ] Estágio da cadeia identificado antes de diagnosticar "dado ausente"
- [ ] Nenhuma composição manual de estágios diferentes no frontend
