---
name: web-vitals
description: Use ao avaliar performance percebida real do Mplacas (LCP, INP, CLS) quando houver ferramenta de medição disponível — o app é pequeno e leve por design, então isso raramente é o gargalo, mas serve para validar mudanças grandes de layout.
---

# Web Vitals — Mplacas

## Finalidade
Verificar performance percebida real quando há ferramenta disponível para medir (ex: Chrome DevTools, Lighthouse), sem inventar número.

## Quando usar
- Após uma mudança grande de layout/quantidade de conteúdo na primeira tela.
- Quando o usuário reportar lentidão percebida.

## Métricas relevantes
- **LCP** (Largest Contentful Paint): tempo até o maior elemento visível renderizar — no Mplacas, tipicamente o hero/dashboard.
- **INP** (Interaction to Next Paint): responsividade a interação (clique no seletor de usina, toggle de seção).
- **CLS** (Cumulative Layout Shift): elementos não devem pular de posição após carregar (ex: skeleton de tamanho diferente do conteúdo real).

## Procedimento
1. Só meça se houver ferramenta real disponível nesta sessão — não estime ou invente número.
2. Se não houver navegador/ferramenta disponível, declare a limitação explicitamente em vez de afirmar que a validação foi feita.
3. CLS: skeletons/loading states devem reservar o mesmo espaço que o conteúdo final ocupa, para não causar salto de layout.
4. Priorize corrigir CLS (fácil de causar sem perceber) sobre otimização de LCP em microssegundos.

## Anti-patterns
- Afirmar "melhorei a performance" sem ter medido antes/depois.
- Skeleton de altura diferente do card real (causa CLS).

## Checklist
- [ ] Medição real feita, ou limitação declarada explicitamente
- [ ] Nenhum salto de layout perceptível introduzido
