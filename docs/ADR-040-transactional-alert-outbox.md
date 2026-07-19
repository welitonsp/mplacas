# ADR-040 - Outbox transacional para entrega de alertas

## Status

Aceito.

## Contexto

Os alertas eram enviados ao Telegram diretamente durante o pipeline. O ledger SQL impedia nova
entrega depois de uma confirmação registrada, mas não eliminava a janela entre o commit dos dados e
a chamada externa. Uma interrupção podia perder o alerta; uma confirmação externa seguida de falha
no banco podia exigir nova entrega sem estado recuperável.

O barramento em memória do ADR-004 continua adequado para efeitos internos síncronos, porém não é
uma fronteira confiável entre processo e provedor externo.

## Decisão

1. Persistir cada intenção de alerta na tabela genérica `outbox_events`, na mesma transação dos dados
   que originaram a avaliação.
2. Armazenar somente payload sanitizado, referência de destino derivada por hash e checksum SHA-256;
   tokens e identificadores reais do chat não entram na outbox.
3. Usar chave de deduplicação única por provedor, destino e fingerprint do alerta.
4. Confirmar a transação antes de chamar o Telegram.
5. Reclamar eventos com estado `PROCESSING` e lock temporal. No PostgreSQL, usar
   `FOR UPDATE SKIP LOCKED`; locks abandonados voltam a ser elegíveis após o timeout configurado.
6. Marcar ledger e evento como entregues na mesma transação após o aceite do provedor.
7. Em falha controlada, retornar o evento a `PENDING`, incrementar tentativas e aplicar backoff
   exponencial de 1 minuto até o teto de 1 hora.
8. Encerrar em `FAILED` após `MPLACAS_OUTBOX_MAX_ATTEMPTS`; nunca incluir texto de erro externo no
   banco, apenas o código sanitizado da classe de falha.
9. Disponibilizar `python -m mplacas.cloud_jobs dispatch-outbox` para recuperar eventos de processos
   anteriores, em lote configurável.
10. Manter o ledger existente como idempotência na ponta. A garantia é de entrega pelo menos uma
    vez: uma interrupção depois do aceite externo e antes do commit pode produzir repetição, nunca
    perda silenciosa.
11. Usar `INSERT ... ON CONFLICT DO NOTHING` em PostgreSQL e SQLite para preservar a transação de
    origem durante concorrência de deduplicação.

## Consequências

### Positivas

- Dados de origem e intenção de entrega passam a ter uma fronteira atômica.
- Eventos pendentes sobrevivem a reinício, falha do Telegram e encerramento do Cloud Run Job.
- Tentativas, próximo horário, erro sanitizado e estado final ficam auditáveis.
- Workers concorrentes não precisam de coordenação em memória.
- O ledger continua impedindo envio quando uma entrega anterior já foi confirmada.

### Negativas

- O banco recebe uma tabela e uma máquina de estados adicionais.
- A entrega pode ocorrer mais de uma vez na rara janela entre aceite externo e commit local.
- A operação precisa agendar o worker `dispatch-outbox` para recuperar backlog independentemente do
  pipeline diário.
- Eventos com payload corrompido ou tentativas esgotadas exigem investigação operacional.

## Validação

A entrega deve permanecer coberta por:

- migration reversível e índices para polling;
- rollback atômico da intenção não confirmada;
- deduplicação concorrente sem rollback da transação externa;
- comprovação de commit antes da chamada ao provedor;
- sucesso conjunto de ledger e outbox;
- retry com backoff, recuperação de lock abandonado e limite de tentativas;
- rejeição de payload adulterado antes da entrega;
- comando de worker e configuração validada;
- Ruff, Mypy, Pytest e smoke test do contêiner.
