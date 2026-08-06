---
name: frontend-performance
description: Use ao avaliar impacto de performance de uma mudança no frontend Mplacas — o projeto tem orçamento de bundle apertado (~99kB gzip total antes das melhorias de gráfico); toda mudança relevante mede antes/depois via npm run build.
---

# Frontend Performance — Mplacas

## Finalidade
Manter o app leve por decisão deliberada, medindo em vez de assumir.

## Quando usar
- Antes/depois de qualquer mudança que adicione componente, dependência ou lógica nova de renderização.

## Procedimento
1. Rode `npm run build` antes da mudança e depois, leia o tamanho gzip de cada chunk no output do Vite — não estime, meça.
2. Orçamento de referência: cada primitiva de gráfico nova (SVG puro) deve custar poucos kB gzip (a primeira leva, Gauge+BarList, custou ~0,1kB; aplicar em 4 cards custou ~0,9kB) — se uma mudança pequena custar muito mais que isso, investigue por quê antes de aceitar.
3. Evite re-render desnecessário: contexto (`AuthContext`, `PlantContext`) só deve disparar re-render de consumidores quando o valor relevante realmente muda — não passe um objeto novo a cada render sem necessidade.
4. Prefira código já usado no projeto (ex: `vectorEffect="non-scaling-stroke"` já provado em `ProductionHistoryChart`) a reinventar técnica de renderização SVG.
5. Nenhuma dependência nova sem justificar o custo em kB gzip explicitamente.

## Anti-patterns
- Adicionar lib pesada "para ganhar tempo de desenvolvimento" sem medir o custo real.
- Otimizar sem medir primeiro (assumir gargalo em vez de perfilar).

## Checklist
- [ ] Bundle medido antes/depois via `npm run build`
- [ ] Delta reportado explicitamente na entrega
- [ ] Nenhuma dependência nova sem justificativa de custo
