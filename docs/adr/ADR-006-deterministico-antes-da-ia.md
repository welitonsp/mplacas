# ADR-006 — Motores determinísticos antes da IA

## Estado

Aceito.

## Contexto

Produção, créditos, faturas, qualidade e anomalias exigem rastreabilidade. Uma LLM não pode ser a autoridade de cálculo ou a origem de fatos operacionais.

## Decisão

O fluxo obrigatório será: validação determinística, regras de negócio, estatística e somente depois explicação por IA. Cada resposta deverá indicar fontes, período, hipóteses e natureza do dado.

## Consequências

- cálculos são reproduzíveis e versionáveis;
- IA não altera registros nem consolida valores;
- linguagem natural pode evoluir sem mudar os resultados matemáticos;
- casos ambíguos exigem confirmação humana.
