---
name: frontend-testing
description: Use ao escrever testes de frontend no Mplacas (Vitest + Testing Library) — padrão já estabelecido (fireEvent, não user-event; mocks de contexto; teste de comportamento observável, não implementação).
---

# Frontend Testing — Mplacas

## Finalidade
Manter consistência de estilo de teste e garantir que testes provam comportamento real, não só "não lança exceção".

## Padrão já estabelecido
- `fireEvent` do Testing Library (não `@testing-library/user-event`, que não é dependência do projeto).
- Mock de contexto via wrapper (`PlantContext`, `AuthContext`) quando o componente sob teste depende deles — ver `AppHeader.test.tsx` como referência.
- Teste de acessibilidade via query por `role`/`aria-label`, não por classe CSS.
- Teste de contrato de API (parser) cobre: payload válido, payload com campo `null`/indisponível, payload malformado.

## Procedimento
1. Antes de escrever um teste novo, `Grep` por um teste equivalente existente para replicar o padrão exato.
2. Teste prova comportamento observável: valor renderizado, atributo ARIA correto, callback chamado com o argumento certo — nunca só "o componente montou sem erro".
3. Para gráfico (`Gauge`, `BarList`, etc.): teste o cálculo real (ex: `strokeDasharray` correto para um valor dado), não só a presença do elemento.
4. Rode a suíte inteira (`npm run test`, sem filtro) antes de considerar a tarefa concluída — não só o arquivo novo.

## Anti-patterns
- Teste que só verifica "não lançou exceção".
- Usar `@testing-library/user-event` (não é dependência instalada).
- Testar por seletor de classe CSS em vez de role/aria.

## Checklist
- [ ] Padrão do projeto seguido (fireEvent, mocks de contexto)
- [ ] Teste prova comportamento real, não só ausência de erro
- [ ] Suíte inteira rodada, não só o arquivo novo
