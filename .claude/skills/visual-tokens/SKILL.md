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
Valores da ADR-077 (verde `#009C77` = energia; marinho `#00406E` = estrutura/rede/ação), definidos
em `:root` e `:root[data-theme="dark"]` e espelhados em `frontend/src/test/designTokens.ts`.
- **Marca**: `--color-brand-primary`, `--color-brand-primary-dark`, `--color-brand-primary-light`, `--color-on-brand` (texto/ícone SOBRE fundo de marca — nunca `text-white` fixo).
- **Superfície**: `--color-surface` (cartão), `--color-surface-subtle` (fundo da página), `--color-surface-sunken` (área rebaixada dentro do cartão), `--color-border`.
- **Texto**: `--color-text-primary`, `--color-text-secondary` (aliases `--color-text`, `--color-text-muted`).
- **Escala de cinza fria**: `--color-gray-50` … `--color-gray-950`, redefinida nos dois temas (substitui o cinza neutro do Tailwind).
- **Severidade** (reservada a estado, nunca decoração): preenchimentos `--color-success`, `--color-warning`, `--color-danger` + pares `-light`; para TEXTO use `--color-success-text`, `--color-warning-text`, `--color-danger-text`.
- **Gráfico**: `--color-chart-reference`, `--color-chart-track`, `--color-chart-grid`, `--color-chart-unassessed`, `--color-data-secondary`/`-light` (dado não-julgado, ex: irradiância).
- **Energia**: `--color-energy-solar`/`-light`, `--color-energy-grid`, `--color-energy-consumption`, `--color-energy-export` (exceção de contraste documentada na ADR-077: sempre com rótulo e kWh).
- **Forma**: `--shadow-card`, `--radius-card`, `--radius-control`.
- **Utilitários Tailwind (`@theme inline`)**: `bg-page`, `bg-card`, `bg-sunken`, `border-line`, `text-ink`, `text-muted`, `bg-brand`, `bg-brand-soft`, `text-brand-ink`, `bg-solar`, `bg-grid-energy`, `font-display`. Prefira-os em componente novo.

## Procedimento
1. Leia `frontend/src/index.css` para confirmar o valor/nome atual — não confie em memória de sessão anterior.
2. Cor de severidade é usada SOMENTE para comunicar estado (bom/atenção/crítico) — nunca para decoração ou identidade visual de uma seção.
3. Token novo só se nenhum existente cobre o caso semântico. Ao criar, siga a convenção de nome já usada (`--color-<categoria>-<variante>`).
4. Contraste mínimo (WCAG AA): 4.5:1 texto normal, 3:1 elementos gráficos/controles — confira antes de introduzir uma combinação nova (ver `wcag-aa`).
5. Token novo ou valor alterado: atualize os DOIS temas no `index.css` e o espelho em `src/test/designTokens.ts`; rode `npx vitest run src/test/contrastRatio.test.ts src/test/designTokensMirror.test.ts`.

## Anti-patterns
- Hex solto (ex.: `#00406e`) em JSX em vez de `var(--color-brand-primary)`/classe Tailwind mapeada.
- `bg-white`, `text-white`, `ring-black/5` ou cinza fixo que não muda com o tema.
- Usar `--color-danger-text` para algo que não é um estado de erro/severidade real.
- Token novo redundante com um existente sob nome diferente.

## Checklist
- [ ] Nenhuma cor hex solta introduzida
- [ ] Severidade usada só para estado, não decoração
- [ ] Contraste AA confirmado para combinação nova
