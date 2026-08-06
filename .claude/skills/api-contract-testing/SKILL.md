---
name: api-contract-testing
description: Use ao escrever/revisar teste de parser de contrato de API no frontend Mplacas (frontend/src/lib/dashboard/*-contracts.ts) — cobertura obrigatória de payload válido, campo null/indisponível, e payload malformado.
---

# API Contract Testing — Mplacas

## Finalidade
Garantir que todo parser de resposta de API é testado nos três cenários que realmente acontecem em produção.

## Cobertura obrigatória por parser
1. **Payload válido completo** — todos os campos presentes, parser produz o tipo esperado corretamente.
2. **Campo `null`/indisponível** — campos com `*_unavailable_reason` presentes como `null` + motivo — parser preserva a semântica de indisponibilidade, não fabrica valor.
3. **Payload malformado** — campo ausente ou tipo errado — parser rejeita de forma consistente com os demais parsers do projeto (mesmo padrão de erro, ver `photovoltaic-contracts.ts` como referência).

## Procedimento
1. Ao criar contrato novo, siga a convenção de nomes/estrutura já usada nos parsers existentes (`plant-contracts.ts`, `photovoltaic-contracts.ts`).
2. Teste de payload malformado confirma que o erro é lançado de forma previsível (mensagem/tipo consistente), não que "algo dá errado".
3. Nenhum parser deve silenciosamente aceitar um payload malformado como se fosse válido preenchendo default.

## Anti-patterns
- Parser que aceita campo ausente e preenche com `0`/string vazia sem sinalizar erro.
- Testar só o caminho feliz.

## Checklist
- [ ] Três cenários cobertos (válido, indisponível, malformado)
- [ ] Convenção de erro consistente com os demais parsers
