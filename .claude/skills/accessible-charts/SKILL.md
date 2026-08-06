---
name: accessible-charts
description: Use ao tornar um gráfico SVG (Gauge, BarList, Sankey etc.) do Mplacas acessível — role="img"/aria-label textual equivalente, alternativa tabular, e por que cor sozinha nunca basta num gráfico.
---

# Accessible Charts — Mplacas

## Finalidade
Garantir que um gráfico SVG puro (sem lib) seja tão acessível quanto uma tabela de números, não menos.

## Quando usar
- Ao criar qualquer primitiva ou instância de gráfico (ver `chart-standards`).

## Procedimento
1. Todo `<svg>` de gráfico tem `role="img"` e `aria-label` com o **equivalente textual completo** do que o gráfico comunica (ex: "Índice de saúde: 82 de 100", não só "gráfico de saúde").
2. Quando o gráfico representa múltiplos pontos/categorias (`BarList`, futura `Sparkline`), cada item individual também é acessível — via `role="progressbar"` com `aria-valuenow/min/max/label` por item (padrão já usado em `MetricCard`/`BarList`), não só um rótulo geral no container.
3. Nunca comunique estado (severidade, tendência) só por cor — todo gráfico tem o valor numérico e/ou texto explícito junto (ex: seta ▲/▼ além da cor verde/vermelha).
4. Para gráfico complexo (Sankey, fluxo com múltiplos nós), considere uma alternativa tabular oculta (`sr-only`) com os mesmos valores, para leitor de tela que não navega bem SVG complexo.
5. Estado neutro/não-avaliável (valor `null`) tem seu próprio `aria-label` explicando a ausência, não um valor de 0 silencioso.

## Anti-patterns
- `<svg>` sem `role`/`aria-label`, mudo para leitor de tela.
- Severidade comunicada só pela cor do preenchimento do anel.
- Gráfico de fluxo (Sankey) sem nenhuma alternativa textual.

## Checklist
- [ ] `role="img"` + `aria-label` textual completo em todo SVG de gráfico
- [ ] Itens individuais de lista/série com ARIA próprio
- [ ] Nunca só cor para comunicar estado
- [ ] Estado nulo tem `aria-label` próprio, não fica mudo
