---
name: accessible-components
description: Use ao criar qualquer componente interativo (botão, dropdown, menu, toggle, formulário) no Mplacas — define o padrão ARIA/teclado já estabelecido no projeto (ex AppHeader user menu, PasswordField toggle) para replicar, não reinventar.
---

# Accessible Components — Mplacas

## Finalidade
Garantir que todo componente interativo novo segue o mesmo padrão de acessibilidade já provado no projeto, em vez de reinventar (e possivelmente errar) a cada vez.

## Quando usar
- Ao criar um componente interativo novo (dropdown, menu, modal, toggle, formulário).

## Padrões já estabelecidos no projeto (replicar)
- **Menu suspenso** (`AppHeader.tsx`, menu de usuário): `aria-haspopup="menu"`, `aria-expanded`, `aria-controls`; fecha com `Escape` (retorna foco ao botão) e clique fora; listeners só registrados quando aberto (sem vazamento entre renders).
- **Toggle de senha visível** (`LoginPage.tsx`): `<button type="button">`, `aria-pressed`, nome acessível textual (não ícone sem label), alterna `type` sem alterar o valor digitado.
- **Erro de formulário associado a campo**: `role="alert"` no container de erro, `aria-invalid`/`aria-describedby` nos campos relacionados via `useId()`.
- **Seção colapsável** (`TechnicalPerformanceSection.tsx`): cabeçalho clicável envolvido em heading (`<h2><button aria-expanded aria-controls>...`), conteúdo com `hidden` (não `display:none` via CSS solto) quando recolhido.
- **Skip link** (`AppShell.tsx`): primeiro elemento focável, `sr-only focus:not-sr-only`, aponta para o `id` do `<main>`.

## Procedimento
1. Antes de criar um componente interativo, procure se já existe um padrão equivalente na lista acima ou no código — reutilize a técnica.
2. Todo controle interativo tem nome acessível (texto visível, `aria-label`, ou `aria-labelledby`) — nunca só ícone sem alternativa textual.
3. Todo estado (expandido/recolhido, pressionado, inválido) é comunicado via atributo ARIA, não só visualmente por cor/posição.
4. Foco visível sempre (`focus-visible:ring`, token já usado no projeto) — nunca remover outline sem substituto.

## Anti-patterns
- `<div onClick>` fazendo o papel de botão sem `role`/teclado.
- Ícone sozinho sem `aria-label`.
- Remover `outline` sem `focus-visible` equivalente.

## Checklist
- [ ] Padrão existente reutilizado quando aplicável
- [ ] Nome acessível presente
- [ ] Estado comunicado via ARIA
- [ ] Foco visível preservado
