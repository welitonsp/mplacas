---
name: design-system
description: Use ao criar ou consolidar componentes-base/tokens do Mplacas. Complementa a skill frontend-design (que já documenta a paleta/padrão de card estabelecidos) com as regras de governança do design system — quando criar token novo, quando não duplicar componente, quando abrir exceção para lib externa.
---

# Design System — governança

## Finalidade
Evitar duplicação de componente/token e decidir com critério quando algo genuinamente precisa ser novo.

## Quando usar
- Antes de criar qualquer componente-base novo (`frontend/src/components/*` que não é específico de uma feature).
- Antes de adicionar uma variável de cor/espaçamento nova em `index.css`.

## Relação com `frontend-design`
Leia `frontend-design` primeiro — ela documenta a paleta, tokens e padrão de card já em vigor. Esta skill (`design-system`) é sobre o PROCESSO de evolução do design system, não sobre o conteúdo atual dele.

## Procedimento
1. **Antes de criar componente**: `Grep` por nome/função equivalente em `frontend/src/components/`. Se existir algo próximo, estenda-o (prop nova) em vez de duplicar.
2. **Antes de criar token novo**: confirme que nenhum token existente já serve (ex: não crie `--color-warning-text-2` se `--color-warning-text` já resolve). Token novo só quando o caso semântico é genuinamente distinto.
3. **Biblioteca externa de UI/componente**: proibida sem ADR explícito — mesmo padrão de proibição já aplicado a bibliotecas de gráfico.
4. Todo componente-base documenta seus estados (default/hover/focus/disabled/loading/error) no próprio arquivo ou em teste, não só no código sem comentário.
5. Dark mode foi implementado (ADR-071) — novos componentes precisam respeitar tanto a paleta clara quanto a escura (`:root[data-theme="dark"]` em `index.css`). Ao adicionar cor/fundo novo, garanta contraste mínimo AA em ambos os temas.

## Anti-patterns
- Dois componentes de card com a mesma função e nomes diferentes.
- Cor hex solta em JSX sem token.
- Adicionar Material UI/Chakra/Ant Design "para ir mais rápido" sem ADR.

## Checklist
- [ ] Nenhum componente duplicado (Grep feito antes de criar)
- [ ] Token novo genuinamente necessário, não redundante
- [ ] Nenhuma lib de UI nova sem ADR
- [ ] Componente novo respeita dark mode (contraste AA em ambos os temas)
