---
name: visual-tokens
description: Use ao adicionar, ler ou alterar variáveis CSS de design token no Mplacas (frontend/src/index.css) — lista os tokens existentes por categoria (marca, superfície, texto, severidade, dado) e a regra de quando um novo é justificado.
---

# Visual Tokens — Mplacas

## Finalidade
Referência rápida dos tokens já definidos em `frontend/src/index.css`, para não redefinir ou duplicar.

## Quando usar
- Antes de escrever qualquer cor/valor visual em um componente novo.

## Categorias existentes (confirme o valor atual lendo `index.css` — pode ter mudado)
- **Marca**: `--color-brand-primary`, `--color-brand-primary-dark`, `--color-brand-primary-light`.
- **Superfície**: `--color-surface`, `--color-surface-subtle`, `--color-border`.
- **Texto**: `--color-text-primary`, `--color-text-secondary`.
- **Severidade** (reservada a estado, nunca decoração): `--color-success-text`, `--color-warning-text`, `--color-danger-text`, e os pares `-light` de fundo.
- **Gráfico**: `--color-chart-reference`, `--color-chart-track`, `--color-data-secondary` (dado não-julgado, ex: irradiância, não é "bom" nem "ruim").

## Procedimento
1. Leia `frontend/src/index.css` para confirmar o valor/nome atual — não confie em memória de sessão anterior.
2. Cor de severidade é usada SOMENTE para comunicar estado (bom/atenção/crítico) — nunca para decoração ou identidade visual de uma seção.
3. Token novo só se nenhum existente cobre o caso semântico. Ao criar, siga a convenção de nome já usada (`--color-<categoria>-<variante>`).
4. Contraste mínimo (WCAG AA): 4.5:1 texto normal, 3:1 elementos gráficos/controles — confira antes de introduzir uma combinação nova (ver `wcag-aa`).

## Anti-patterns
- Hex solto (`#1a56db`) em JSX em vez de `var(--color-brand-primary)`/classe Tailwind mapeada.
- Usar `--color-danger-text` para algo que não é um estado de erro/severidade real.
- Token novo redundante com um existente sob nome diferente.

## Checklist
- [ ] Nenhuma cor hex solta introduzida
- [ ] Severidade usada só para estado, não decoração
- [ ] Contraste AA confirmado para combinação nova
