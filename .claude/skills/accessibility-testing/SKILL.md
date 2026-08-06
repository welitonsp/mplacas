---
name: accessibility-testing
description: Use ao escrever teste que valida acessibilidade no Mplacas — contraste (colorContrast.test.tsx), ARIA, navegação por teclado. Complementa wcag-aa (o checklist) com como testar cada item automatizadamente.
---

# Accessibility Testing — Mplacas

## Finalidade
Transformar o checklist de `wcag-aa` em testes automatizados que travam regressão.

## Procedimento
1. **Contraste**: o projeto já tem um guard de regressão (`colorContrast.test.tsx`) que varre classes de cor proibidas (ex: `text-gray-400`) no código-fonte — ao introduzir uma cor nova, rode esse teste antes de tudo.
2. **ARIA**: teste presença e valor correto de `role`, `aria-label`, `aria-expanded`, `aria-valuenow` etc. via query do Testing Library (`getByRole`), não `querySelector` genérico.
3. **Teclado**: simule `fireEvent.keyDown` com `Escape`/`Tab`/`Enter` para componentes interativos (menu, toggle) e confirme o comportamento esperado (fecha, alterna, ativa).
4. **Foco**: teste que o elemento certo recebe foco após uma ação (ex: `Escape` no menu devolve foco ao botão que abriu).

## Anti-patterns
- Testar acessibilidade só visualmente/manualmente sem teste automatizado que trave regressão futura.
- Assumir que `role="progressbar"` está certo sem testar os atributos `aria-valuenow/min/max` junto.

## Checklist
- [ ] Guard de contraste rodado para toda cor nova
- [ ] ARIA testado via `getByRole`, não seletor genérico
- [ ] Comportamento de teclado testado explicitamente
