---
name: definition-of-done
description: Use como critério final antes de reportar qualquer tarefa do Mplacas como concluída — combina quality-gates com os critérios de produto (nenhum dado estimado como confirmado, nenhum cálculo oficial no frontend/LLM, documentação atualizada quando aplicável).
---

# Definition of Done — Mplacas

## Finalidade
Critério único e verificável de "pronto", para não fechar tarefa com trabalho parcial.

## Uma tarefa só está concluída quando
- Objetivo funcional real atendido (não só "código roda").
- `quality-gates` completo e verde (backend e/ou frontend, conforme aplicável).
- Nenhuma duplicação desnecessária introduzida.
- Nenhum segredo no código/log/estado persistente.
- Estados de UI obrigatórios implementados (loading, vazio, erro, indisponível, parcial) quando a tarefa toca UI.
- Responsividade validada (ou limitação declarada — ver `visual-regression`).
- Acessibilidade validada (`wcag-aa`).
- Erros de terceiro sanitizados.
- Observabilidade/auditoria preservada (nada removido sem necessidade).
- Documentação/ADR atualizado quando a mudança altera uma decisão registrada.
- Critério de aceite original comprovado, não assumido.
- Revisão independente concluída quando a área de risco exigir (`secure-code-review`).
- Nenhum dado estimado apresentado como confirmado (`data-quality-ui`).
- Nenhum cálculo oficial (energético, financeiro) transferido para o frontend ou para um LLM explicativo.

## Procedimento
1. Percorra a lista item a item antes de reportar "concluído" — não pule para "parece pronto".
2. Se algum item não se aplica à tarefa específica, declare isso explicitamente em vez de omitir.
3. Nunca marque como concluído se: testes falhando, implementação parcial, erro não resolvido, ou dependência/arquivo necessário não encontrado.

## Anti-patterns
- Reportar "concluído" com testes vermelhos "porque não é culpa desta mudança" sem investigar.
- Pular item da lista por pressa.

## Checklist
- [ ] Todos os itens da lista percorridos
- [ ] Itens não aplicáveis declarados como tal, não omitidos
- [ ] Nenhum item crítico pulado
