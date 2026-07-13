# ADR-023 — Runtime operacional do pipeline diário

## Status

Aceito.

## Contexto

A PR nº 26 criou o ledger persistente e o lock por usina/data. Faltava integrar esse controle à execução real do pipeline, registrar duração, recuperar locks abandonados e disponibilizar execução e estado consultáveis sem expor dados privados.

## Decisão

1. Toda execução operacional adquire o lock persistente antes de coletar clima ou enviar alertas.
2. O serviço marca estágios técnicos e conclui o registro como `SUCCEEDED` ou `FAILED`.
3. Falhas persistem somente um código derivado do tipo da exceção, sem mensagem externa, token, coordenadas ou payload.
4. A duração é medida com relógio monotônico e devolvida como métrica operacional.
5. O endpoint operacional controla explicitamente `commit` e `rollback`.
6. Uma consulta separada retorna apenas o snapshot técnico da execução mais recente por usina.
7. Um registro `RUNNING` somente pode ser retomado quando ultrapassa o timeout configurado por `MPLACAS_PIPELINE_STALE_LOCK_TIMEOUT_MINUTES`.
8. A retomada incrementa o contador de tentativas e preserva a rastreabilidade no mesmo registro lógico por usina/data.
9. Os endpoints `POST /pipeline/run` e `GET /pipeline/status/latest` exigem a credencial operacional existente.
10. Respostas e logs expõem somente identificadores técnicos, estágios, duração e contagens agregadas.

## Consequências

- execuções são auditáveis de ponta a ponta;
- concorrência duplicada permanece bloqueada;
- processos interrompidos podem ser retomados após timeout explícito;
- falhas podem ser retentadas sem persistir conteúdo sensível;
- endpoints e schedulers compartilham o mesmo runtime;
- métricas de duração ficam disponíveis para observabilidade e SLO.

## Segurança

Nenhuma credencial, identificador bruto de destino, coordenada, fatura ou resposta de provedor é registrada no ledger, nas respostas ou nos logs estruturados.
