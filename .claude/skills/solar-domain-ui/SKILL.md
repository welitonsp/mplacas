---
name: solar-domain-ui
description: Use ao exibir qualquer indicador fotovoltaico (PR, yield, performance ratio, perdas, expectativa de produção) no Mplacas — nomenclatura e convenções corretas do domínio, alinhadas ao que o backend calcula (ADR-057, ADR-061, ADR-068). Nunca a UI recalcula, só apresenta.
---

# Solar Domain UI — Mplacas

## Finalidade
Evitar rótulo de UI que não corresponde ao que o backend realmente calcula, ou composição indevida de grandeza física no frontend.

## Quando usar
- Ao criar/editar qualquer card de performance, perdas, produção esperada.

## Convenções confirmadas (verifique contra o backend antes de assumir)
- **Azimute**: `0° = norte, 90° = leste, 180° = sul, 270° = oeste` (ADR-057) — sentido horário a partir do norte.
- **Performance Ratio (PR)**: já vem calculado do backend (`photovoltaic/performance.py`), inclusive a versão corrigida por temperatura — a UI nunca recalcula, só formata.
- **Produção esperada**: desde o ADR-068, calculada inteiramente no backend (`resolve_expected_daily_production`) — a UI só lê `expected_daily_production_kwh`/`*_unavailable_reason`, nunca deriva localmente (`deriveExpectedDailyProduction` foi removida por essa razão).
- **Taxonomia de perdas**: 8 categorias fixas na ordem definida pelo backend (COMMUNICATION, UNAVAILABILITY, CLIPPING, SOILING, SHADING, TEMPERATURE, DEGRADATION, UNEXPLAINED — ADR-065 §4) — a UI preserva essa ordem, nunca reordena por severidade/valor.
- **Baseline sazonal**: requer 366 dias de histórico corrido (`REFERENCE_YEAR_INCOMPLETE` até lá) — não é bug, é o desenho; a UI trata isso como estado explícito, não como erro.
- **`NOT_ASSESSABLE` vs `NOT_DETECTED`**: são estados semanticamente diferentes (dado insuficiente vs. avaliado e ausente) — nunca colapsar os dois na mesma representação visual sem diferenciação.

## Procedimento
1. Antes de rotular um indicador novo na UI, confirme o nome/definição exata no endpoint/serviço backend correspondente (`src/mplacas/photovoltaic/`) — não invente nomenclatura.
2. Nunca componha grandezas físicas no frontend (multiplicar capacidade × irradiância × performance, por exemplo) — isso violaria ADR-012/068.
3. Ao mostrar uma categoria de perda sem evidência suficiente (`NOT_ASSESSABLE`), explique por que (ex: "requer telemetria de intervalo, indisponível hoje"), não deixe um espaço vazio sem contexto.

## Anti-patterns
- Recalcular PR ou produção esperada no cliente.
- Reordenar as 8 categorias de perda por valor/severidade.
- Confundir `NOT_ASSESSABLE` com `NOT_DETECTED` na mesma cor/ícone.

## Checklist
- [ ] Nomenclatura confirmada contra o backend real
- [ ] Nenhuma composição de grandeza física no frontend
- [ ] Ordem de categorias de perda preservada
- [ ] `NOT_ASSESSABLE` e `NOT_DETECTED` diferenciados
