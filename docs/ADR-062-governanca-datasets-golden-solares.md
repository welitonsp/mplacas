# ADR-062 — Governança e gates para datasets golden solares

Status: Aceito — 2026-08-02

## Contexto

Testes sintéticos protegem contratos de software, mas não medem desempenho diagnóstico no mundo real.
Chamar fixtures criadas pelos desenvolvedores de “validadas por especialista” produziria evidência
circular. Casos de campo, por outro lado, podem carregar identificadores comerciais ou pessoais.

## Decisão

Datasets solares seguem o contrato `MPLACAS_SOLAR_GOLDEN_V1` e distinguem explicitamente:

- `SYNTHETIC_REGRESSION`: protege comportamento determinístico, nunca libera o gate científico;
- `ANONYMIZED_FIELD`: caso derivado de campo, elegível somente após revisão registrada;
- revisão `PENDING` ou `APPROVED`, com papel do revisor, data com timezone e referência da evidência;
- label `POSITIVE`, `NEGATIVE` ou `NOT_ASSESSABLE` para cada categoria da taxonomia;
- valores decimais serializados como texto para evitar drift binário.

O carregador rejeita campos identificadores conhecidos em qualquer nível do JSON e impede aprovação de
casos sintéticos. O avaliador calcula TP, FP, FN, TN, abstenções, cobertura, precisão, recall, taxa de
falso positivo e taxa de falso negativo por categoria.

## Gate de liberação

Para cada categoria são exigidos pelo menos cinco labels positivos e cinco negativos, precisão e
recall mínimas de 80%, cobertura mínima de 90% e taxas de falso positivo/negativo máximas de 20%.
O dataset inteiro deve estar aprovado por especialista solar. Arquivos aprovados adicionados ao
diretório golden passam automaticamente por esse gate na suíte.

## Estado inicial

O repositório contém somente `solar-loss-taxonomy-synthetic-candidates-v1`, com revisão `PENDING`.
Ele protege a implementação, mas não satisfaz a validação humana requerida pela SOL-06. O checklist
deve permanecer parcial até a incorporação controlada dos casos de campo.
