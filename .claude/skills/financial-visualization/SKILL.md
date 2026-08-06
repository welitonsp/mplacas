---
name: financial-visualization
description: Use ao criar gráficos/visualizações de dado financeiro no Mplacas (economia, ROI, decomposição de fatura). Complementa chart-standards e financial-display-rules com regras específicas de dinheiro — nunca inventar decomposição sem validar contra o parser real, sempre moeda visível.
---

# Financial Visualization — Mplacas

## Finalidade
Evitar que uma visualização financeira (barra empilhada de fatura, arco de ROI) apresente uma decomposição que não bate com o dado real do backend.

## Quando usar
- Ao criar gráfico de decomposição de fatura, retorno do investimento, economia.

## Procedimento
1. Antes de decompor um valor total em partes visuais (ex: barra empilhada de `total_amount_brl` = energia + iluminação + outros), **valide contra o parser/serviço real** que a soma das partes realmente bate com o total em casos reais — nunca assuma. Se a soma pode estourar o total em algum cenário de fatura real, a barra mentiria; trate isso como bug de dado a resolver antes do gráfico, não como detalhe visual.
2. Todo valor monetário no gráfico mostra moeda (R$) e o rótulo textual completo ao lado/tooltip — a barra nunca é a única fonte da informação exata.
3. Retorno do investimento (ROI, payback) sem investimento cadastrado é um estado explícito ("sem investimento registrado"), nunca um gráfico vazio ou com 0%.
4. Nunca calcule um valor financeiro novo no frontend para popular o gráfico — todo número vem pronto do backend.

## Anti-patterns
- Barra empilhada cuja soma das partes não bate com o total real em algum caso de fatura.
- Anel de progresso de payback mostrando 0% quando o real é "investimento não cadastrado".

## Checklist
- [ ] Decomposição validada contra dado real, não assumida
- [ ] Moeda sempre visível
- [ ] Estado de "sem investimento" tratado explicitamente
- [ ] Nenhum cálculo financeiro novo no frontend
