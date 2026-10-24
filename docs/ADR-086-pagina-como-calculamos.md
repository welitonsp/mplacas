# ADR-086 — Página "Como calculamos"

## Status

**Aceito — 2026-10-24.** Item 3 do plano aprovado pelo dono depois da revisão dos cálculos
pelas regras da ANEEL.

## Contexto

Um cliente ou investidor precisa saber de onde vem cada número e com base em que regra ele é
calculado. Essas regras hoje só existem nos ADRs técnicos:
- ADR-080: tarifa cheia;
- ADR-082: dias estimados;
- ADR-084: conferência da distribuidora;
- ADR-085: bandeira e créditos externos.

## Decisão

- **Onde fica:** nova rota `/dashboard/dinheiro/como-calculamos` (`MethodologyPage`). A aba
  Dinheiro fica ativa (o `NavLink` não usa `end`). A rota é carregada sob demanda e tem
  orçamento próprio de 6 kB; o tamanho medido é 2,4 kB.
- **Conteúdo fixo, sem dado da usina**, em cinco blocos:
  1. de onde vem cada número;
  2. placas × distribuidora;
  3. conferência da distribuidora;
  4. economia do ciclo;
  5. limites.

  Cada regra cita a norma de onde vem: REH 3.407/2024 e REH 3.544/2025 (tarifas), Lei
  14.300/2022 (Fio B e créditos de 60 meses) e REN 1.000/2021 (custo de disponibilidade).
  As fórmulas são as mesmas do motor.
- **Acesso:** atalho "Como calculamos" no fim das abas Dinheiro e Energia (`MethodologyLink`).
- **Manutenção:** se uma fórmula do motor mudar, esta página muda junto. O teste
  `MethodologyPage.test.tsx` fixa as fórmulas e as normas citadas.

## Validação

- **Teste de componente:** confere os headings, o link de volta, as normas e as fórmulas.
- **Capturas e2e:** a página entra em `e2e/screenshots.spec.ts` e
  `e2e/overflow.spec.ts` (celular e desktop, sem rolagem lateral).
