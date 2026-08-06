---
name: premium-product-ux
description: Use ao avaliar ou redesenhar qualquer tela do Mplacas do ponto de vista de produto — define o que "premium" significa no projeto (clareza, confiabilidade, hierarquia) e o que NÃO significa (glassmorphism, gradiente, cópia de concorrente). Impede redesign meramente decorativo.
---

# Premium Product UX — Mplacas

## Finalidade
Dar um critério objetivo para "isso parece premium" que não dependa de gosto pessoal nem de copiar a estética de outro produto.

## Quando usar
- Antes de qualquer redesenho visual.
- Ao avaliar uma sugestão de mudança de UI vinda de fora (usuário, relatório externo).

## O que "premium" significa aqui
- Clareza: o usuário entende o dado sem esforço.
- Consistência: mesmo padrão visual em toda a tela, sem duas soluções para o mesmo problema.
- Previsibilidade: o mesmo tipo de ação sempre se comporta igual.
- Confiabilidade: o dado exibido é honesto — nunca fabricado, nunca escondendo indisponibilidade.
- Hierarquia: o que importa mais está mais visível.
- Feedback completo: toda ação tem resposta visual (loading, sucesso, erro).
- Visualização honesta do dado — ver `chart-standards`.

## O que "premium" NÃO significa
- Glassmorphism indiscriminado, gradiente em todo card, sombra pesada.
- Cor decorativa sem função semântica.
- Copiar layout do Stripe/Linear/Apple pixel a pixel — usar como referência de PRINCÍPIO, nunca de layout.
- Dark mode obrigatório.
- Animação constante.
- Adicionar card/elemento visual "porque fica bonito" sem ganho de compreensão.

## Procedimento
1. Toda sugestão de mudança visual responde: "isso ajuda o usuário a entender/decidir mais rápido, ou é só estética?" — se for só estética, declare isso explicitamente.
2. Antes de mudar um padrão visual estabelecido (ex: cor de severidade, esqueleto de card), confirme que não existe um padrão já definido em `frontend-design`/`visual-tokens` sendo contrariado sem necessidade.
3. Toda mudança visual grande é dividida em etapas pequenas revisáveis, nunca um redesenho monolítico de uma vez.

## Anti-patterns
- "Vamos deixar mais parecido com o Stripe" sem dizer qual princípio específico do Stripe está sendo copiado e por quê.
- Adicionar gráfico decorativo que não muda a decisão do usuário.

## Checklist
- [ ] Mudança justificada por clareza/decisão, não só estética
- [ ] Não contraria padrão de token/design já estabelecido sem necessidade
- [ ] Dividida em etapas revisáveis
