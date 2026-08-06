---
name: investment-management-ui
description: Use ao construir/editar telas de cadastro e acompanhamento de investimento (CAPEX) no Mplacas — CapexRegistrationForm e FinancialReturnSection como referência de padrão já implementado (ADR-067).
---

# Investment Management UI — Mplacas

## Finalidade
Manter consistência no fluxo de cadastro e visualização de investimento (CAPEX) da usina.

## Referências já implementadas (ADR-067)
- `CapexRegistrationForm.tsx` — cadastro de `investment_amount_brl`/`investment_recorded_on`.
- `FinancialReturnSection.tsx` — ROI, payback, com dois motivos de indisponibilidade separados (`unavailable_reason` do retorno, `payback_unavailable_reason` do payback).

## Procedimento
1. Antes de criar um formulário de dado financeiro novo, siga o padrão de validação/erro já usado em `CapexRegistrationForm` (contraste de placeholder AA, mensagens de erro associadas via `aria-describedby`).
2. Payback/ROI sem investimento cadastrado nunca vira 0% ou "R$ 0" — é o estado explícito "sem investimento registrado" com uma chamada para ação (cadastrar).
3. Toda mudança de investimento é uma ação auditável — confirme que o backend já registra isso via audit event antes de assumir; não implemente rastreabilidade nova no frontend.

## Anti-patterns
- Mostrar 0% de ROI para "sem dado" em vez do estado explícito.
- Formulário de investimento sem validação de contraste/acessibilidade.

## Checklist
- [ ] Estado "sem investimento" tratado explicitamente
- [ ] Formulário segue padrão de erro/acessibilidade já estabelecido
- [ ] Nenhuma lógica de auditoria duplicada no frontend
