# ADR-008 — Observabilidade persistente de jobs

## Status

Aceito.

## Contexto

Coletas da NEPViewer, consolidação D+1 e backfills precisam ser auditáveis mesmo quando logs efêmeros não estiverem disponíveis.

## Decisão

Cada execução relevante será registrada em `job_runs` com:

- nome do job;
- estado `RUNNING`, `SUCCEEDED` ou `FAILED`;
- início, término e duração;
- registros recebidos e alterados;
- métricas operacionais não sensíveis;
- código e mensagem sanitizada de erro.

O início é confirmado antes da operação. Sucesso ou falha são persistidos ao final. O endpoint `/operations/jobs` expõe somente metadados operacionais seguros.

## Consequências

- histórico operacional independente do provedor de logs;
- cálculo futuro de SLO, taxa de sucesso e latência;
- diagnóstico de jobs travados ou recorrentes;
- maior uso de armazenamento, sujeito a política de retenção futura;
- proibição de credenciais, tokens, CPF, endereço ou conteúdo de faturas nas métricas e mensagens.
