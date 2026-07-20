# ADR-046 - Fila de coleta desacoplada com workers no Postgres

## Status

Aceito.

## Contexto

A coleta de telemetria e a coleta climática executavam de forma síncrona dentro do ciclo do job
diário, por usina, em sequência. Nesse modelo, a falha de uma usina (provedor indisponível, timeout)
interrompia ou degradava o processamento das demais, e o retry era do lote inteiro, não da tarefa.
A auditoria técnica de 16/07/2026 classificou fila/workers como P1.

A decisão de infraestrutura (base da fila) foi avaliada entre uma fila no próprio Postgres e um
serviço gerenciado (Cloud Tasks/Pub-Sub).

## Decisão

1. A fila é implementada **no próprio Postgres**, reaproveitando o padrão já consolidado do outbox
   transacional de eventos: claim atômico com `SELECT ... FOR UPDATE SKIP LOCKED`, recuperação de
   tarefas travadas por `stale_after`, backoff exponencial com teto de 3600s e estados
   `PENDING`/`PROCESSING`/`COMPLETED`/`FAILED`.
2. Nova tabela `collection_tasks` com `deduplication_key` único por `(tipo, usina, data-alvo)`,
   garantindo enfileiramento idempotente (migration `20260719_0015`).
3. Um `CollectionWorker` processa tarefas de um tipo, **isolando a falha de cada uma**: cada tarefa
   roda em sua própria transação e sessão; o commit de uma não é desfeito pela falha de outra, e uma
   usina com erro é reagendada com backoff sem afetar as demais.
4. Cada tarefa é observada por `observe_operation`, herdando logs, spans e métricas
   (ADR-041/ADR-042), com o nome `collection_worker.<tipo>`.

### Por que Postgres e não Cloud Tasks/Pub-Sub

- O enfileiramento e a persistência de dados ocorrem na mesma transação, eliminando o problema de
  dual-write que um broker externo introduziria.
- Reaproveita convenções, testes e operação já existentes no repositório; zero infraestrutura nova
  no bootstrap e custo adicional nulo.
- Um serviço gerenciado só compensaria com alto volume ou workers distribuídos em máquinas
  separadas, o que não corresponde a um job diário reconciliando telemetria de um conjunto pequeno
  de usinas.

A interface de repositório da fila mantém o desacoplamento necessário para uma futura troca de
backend, caso o volume justifique.

## Consequências

### Positivas

- Falha de uma usina não contamina as demais; o retry é por tarefa, com backoff.
- Enfileiramento idempotente evita coletas duplicadas ao reexecutar o disparo.
- Tarefas travadas por processo morto são recuperadas automaticamente após `stale_after`.
- Observabilidade uniforme por tarefa, sem instrumentação nova.

### Negativas

- O polling da fila consome uma consulta por ciclo de worker; os índices de `claimable` mantêm o
  custo baixo.
- Não há workers distribuídos nesta fase; o processamento é de um processo por vez (o
  `SKIP LOCKED` já suporta concorrência quando isso for desejado).

## Validação

- enfileiramento idempotente por `(tipo, usina, data)`;
- claim exclusivo que remove a tarefa do conjunto elegível;
- backoff exponencial no reagendamento e falha após o máximo de tentativas;
- **isolamento de falha entre tarefas**: uma usina com erro é reagendada enquanto a saudável
  conclui;
- recuperação de tarefa travada (`PROCESSING` estagnado) após `stale_after`;
- contrato da migração `20260719_0015` presente e encadeado.
