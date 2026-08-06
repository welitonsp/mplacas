---
name: chart-standards
description: Use ao criar ou modificar qualquer gráfico no Mplacas. Define as primitivas SVG puras já disponíveis (Gauge, BarList e as que vierem depois em frontend/src/components/charts/), a proibição de biblioteca de gráfico nova sem ADR, e as regras de honestidade visual (nunca fabricar zero, sempre eixo/escala legível).
---

# Chart Standards — Mplacas

## Finalidade
Garantir que todo gráfico novo é honesto, acessível e construído sem dependência nova, seguindo o padrão de primitivas já estabelecido.

## Quando usar
- Antes de criar qualquer visualização de dado numérico/percentual nova.
- Antes de "consertar" um card de número puro transformando-o em gráfico.

## Regra inegociável: sem biblioteca de gráfico nova
O projeto constrói todo gráfico em SVG/CSS puro, sem dependência (Chart.js, Recharts, D3 completo, etc.), por decisão explícita registrada (bundle leve, poucas dependências). Qualquer exceção exige ADR novo E confirmação explícita do usuário — nunca decisão unilateral do agente. Antes de considerar uma lib, verifique se uma das primitivas existentes (ou uma nova, também em SVG puro) resolve.

## Primitivas disponíveis em `frontend/src/components/charts/`
- `Gauge.tsx` — anel de progresso circular, valor 0-100, `tone` semântico.
- `BarList.tsx` — lista de barras horizontais proporcionais, com suporte a valor `null` (estado não-avaliável sem fabricar zero).
- (verifique o diretório para as que tiverem sido adicionadas depois desta skill ser escrita — `Bullet`, `StackedBar`, `SankeyFlow`, `Sparkline` fazem parte do plano em andamento).

## Regras de honestidade visual
1. **Nunca fabrique zero.** Um valor `null`/`unavailable_reason` nunca vira barra/anel de 0% — trate como estado visual neutro/tracejado explícito (ver `BarList` como referência de implementação).
2. **Todo gráfico com grandeza numérica real precisa de eixo/escala legível** — barras sem nenhum rótulo de referência (como as antigas barras de 6-8px do projeto) não contam como gráfico de verdade.
3. **Comparação entre duas séries** (ex: real vs. esperado) precisa de codificação visual clara (ex: bullet chart), não dois números soltos lado a lado.
4. **Cor é reservada ao eixo semântico de severidade** (ver `visual-tokens`) — nunca decorativa.
5. **Toda visualização tem alternativa textual/tabular equivalente** acessível (ver `accessible-charts`).
6. Altura mínima de barra: ~16-20px. Barras de 6-8px lêem como decoração, não dado (erro já cometido e corrigido no projeto — não repetir).

## Procedimento
1. Identifique se o card mostra um valor com escala de referência conhecida (percentual, comparação com meta/histórico) — se sim, é candidato a virar gráfico. Valores absolutos sem denominador natural (ex: saldo de créditos em kWh) continuam como número — não force gráfico onde não ajuda.
2. Escolha a primitiva certa: proporção de um total → `BarList`/`StackedBar`; 0-100% único → `Gauge`; real vs. meta → `Bullet`; série temporal → `Sparkline`/gráfico de barras com eixo; fluxo entre nós → `SankeyFlow`.
3. Implemente sem duplicar lógica de primitiva já existente — estenda a primitiva com prop nova se faltar um caso.
4. Reporte o delta de bundle gzip a cada entrega (`npm run build`).

## Anti-patterns
- Adicionar `recharts`/`chart.js` "porque é mais rápido".
- Gráfico decorativo que não ajuda a comparar/entender mais rápido que o número puro.
- Barra/anel fabricado a partir de dado `null`.

## Checklist
- [ ] Nenhuma biblioteca nova sem ADR + confirmação do usuário
- [ ] Nenhum zero fabricado
- [ ] Eixo/escala legível quando há grandeza numérica real
- [ ] Alternativa textual/tabular presente
- [ ] Delta de bundle reportado
