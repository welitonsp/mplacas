# ADR-048 - Retenção de registros operacionais terminais

## Status

Aceito.

## Contexto

As tabelas operacionais crescem indefinidamente: `job_runs`, `pipeline_executions`, `outbox_events`,
`collection_tasks` e o ledger de deduplicação `alert_delivery_records` acumulam um registro por
execução ou evento, sem limite. A auditoria de 2026-07-16 classificou particionamento/retention como
P1. Num contexto single-plant, o particionamento de séries temporais (`daily_energy`, clima) ainda
não se justifica — o volume é de um punhado de linhas por dia. O problema real e imediato é o
acúmulo dos **logs e ledgers operacionais**.

## Decisão

Um `RetentionService` remove registros **terminais e antigos** dessas tabelas, por corte de tempo,
com janelas específicas. Regras invioláveis:

1. **Nunca remove registros não terminais.** Jobs `RUNNING`, execuções `RUNNING`, eventos `PENDING`
   ou `PROCESSING` e tarefas `PENDING`/`PROCESSING` são preservados independentemente da idade.
2. **Nunca toca em dado de produção.** `daily_energy`, observações climáticas e faturas são o objeto
   da reconciliação, não log — ficam fora do serviço por completo.
3. **Janela conservadora para o ledger de alertas.** `alert_delivery_records` deduplica alertas por
   fingerprint; remover um fingerprint ainda relevante permitiria o reenvio de um alerta antigo.
   Sua janela padrão é de 365 dias, contra 30–90 dias dos logs de execução.

Janelas padrão (configuráveis por ambiente):

| Tabela | Janela | Filtro |
|---|---:|---|
| `job_runs` | 90 dias | `SUCCEEDED`/`FAILED`, por `started_at` |
| `pipeline_executions` | 90 dias | `SUCCEEDED`/`FAILED`, por `started_at` |
| `outbox_events` | 30 dias | `DELIVERED`/`FAILED`, por `created_at` |
| `collection_tasks` | 30 dias | `COMPLETED`/`FAILED`, por `created_at` |
| `alert_delivery_records` | 365 dias | por `sent_at` |

O job `retention` no `cloud_jobs` executa a purga; deve ser agendado com baixa frequência
(por exemplo, diária ou semanal) no Cloud Scheduler.

## Consequências

### Positivas

- O crescimento das tabelas operacionais passa a ser limitado, mantendo consultas e custo previsíveis.
- Nenhum dado de produção ou de reconciliação é afetado.
- A deduplicação de alertas permanece íntegra graças à janela longa.

### Negativas

- Registros históricos de execução além da janela deixam de existir; se for necessária retenção de
  longo prazo para auditoria, deve-se arquivar antes (fora do escopo desta fase).
- A purga é por `DELETE` em lote; em volumes muito grandes, poderia exigir paginação — não é o caso
  no contexto atual.

## Não incluído (decisão explícita)

- **Particionamento de séries temporais** (`daily_energy`, clima): adiado. O volume single-plant não
  justifica a complexidade. Revisitar se o produto passar a operar muitas usinas.

## Validação

- apaga apenas registros terminais e mais antigos que a janela;
- preserva jobs/execuções em andamento e tarefas/eventos pendentes, mesmo antigos;
- preserva registros terminais recentes;
- ledger de alertas respeita a janela conservadora de 365 dias;
- janelas validam valores positivos.
