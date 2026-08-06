---
name: wcag-aa
description: Use como checklist de conformidade WCAG 2.2 AA em qualquer tela/componente do Mplacas — contraste, teclado, foco, headings, labels, touch targets, movimento reduzido. Linha de base obrigatória do projeto.
---

# WCAG 2.2 AA — checklist Mplacas

## Finalidade
Checklist objetivo e verificável de acessibilidade nível AA, aplicado a toda tela nova ou alterada.

## Quando usar
- Antes de considerar qualquer entrega de UI concluída.

## Checklist verificável
- **Contraste**: texto normal ≥ 4.5:1; texto grande (≥18pt ou ≥14pt bold) ≥ 3:1; componentes gráficos/controles ≥ 3:1. Existe teste de regressão no projeto (`colorContrast.test.tsx`) — rode e não deixe passar a quebrar.
- **Teclado**: todo controle interativo alcançável e operável só com Tab/Enter/Espaço/Escape, sem mouse.
- **Foco visível**: `focus-visible:ring` (token do projeto) em todo elemento focável; nunca `outline: none` sem substituto.
- **Heading hierarchy**: exatamente um `<h1>` por página; níveis não pulam (h2 antes de h4).
- **Labels**: todo input tem `<label>` associado (`for`/`id`) ou `aria-label`.
- **Nome acessível em ícone-botão**: nunca só ícone, sempre `aria-label` ou texto visível.
- **Touch targets**: controles principais ≥ ~44×44px.
- **`prefers-reduced-motion`**: qualquer animação respeita a preferência do usuário.
- **`aria-live`**: só onde há mudança de conteúdo relevante para anunciar (não abusar).
- **Landmarks semânticos**: `<main>`, `<header>`, `<nav>` usados corretamente.

## Procedimento
1. Rode os testes de acessibilidade/contraste já existentes no projeto antes de qualquer entrega.
2. Para componente novo, percorra o checklist item a item, não confie em "parece acessível".
3. Cor nunca é o único canal de informação de estado (severidade sempre tem texto/ícone junto).

## Anti-patterns
- Remover outline por estética sem `focus-visible` equivalente.
- `<div onClick>` sem `role`/teclado.
- Dois `<h1>` na mesma página.

## Checklist
- [ ] Contraste AA confirmado (teste rodado, não só "parece ok")
- [ ] Navegação por teclado completa
- [ ] Um único `<h1>`, hierarquia sem saltos
- [ ] Nenhum ícone-botão sem nome acessível
