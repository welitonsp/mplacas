# CLAUDE.md — Mplacas

## Roteamento de modelos

Este projeto usa três subagentes com modelos fixados por custo/capacidade.
NUNCA use um modelo mais caro do que a tarefa exige.

| Agente | Modelo | Quando usar |
|---|---|---|
| architect | Opus 4.8 | Planejamento, ADRs, decisões de arquitetura, análise de auditoria, desenho de trade-offs |
| worker | Sonnet 5 | Implementação de código, testes, correção de bugs, ciclo de CI |
| quick-task | Haiku 4.5 | Buscas, resumos, comandos de terminal, formatação, tarefas mecânicas |

## Regra de decisão

Antes de executar qualquer tarefa, pergunte: qual é o menor modelo que resolve isso bem?

1. É uma decisão de arquitetura, um ADR, ou uma tarefa vaga/grande? Delegue ao architect primeiro para desenhar o plano.
2. É implementação de algo já especificado? Delegue ao worker.
3. É busca, leitura, resumo, formatação, ou comando pontual? Delegue ao quick-task.

Nunca peça ao architect (Opus) para implementar código rotineiro.
Nunca peça ao worker (Sonnet) para tomar decisão estrutural sem antes passar pelo architect.
Nunca use worker ou architect para tarefas que o quick-task resolve.

## Fluxo típico de uma feature nova

1. Descreva o objetivo em linguagem natural na conversa principal.
2. A conversa delega ao architect: ele produz o plano em etapas.
3. Você aprova (ou ajusta) o plano.
4. A conversa delega cada etapa ao worker, que implementa e roda o CI.
5. Buscas e verificações pontuais no meio do caminho vão para o quick-task.
