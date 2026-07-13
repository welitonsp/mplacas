# ADR-023 — Runtime operacional do pipeline diário

## Status

Em implementação.

## Contexto

A PR nº 26 criou o ledger persistente e o lock por usina/data. Faltava integrar esse controle à execução real do pipeline, registrar duração e disponibilizar um estado consultável sem expor dados privados.

## Decisão

1. Toda execução operacional adquire o lock persistente antes de coletar clima ou enviar alertas.
2. O serviço marca estágios técnicos e conclui o registro como `SUCCEEDED` ou `FAILED`.
3. Falhas persistem somente um código derivado do tipo da exceção, sem mensagem externa, token, coordenadas ou payload.
4. A duração é medida em memória monotônica e devolvida como métrica operacional.
5. O chamador continua responsável por `commit` ou `rollback`; o domínio não oculta fronteiras transacionais.
6. Uma consulta separada retorna apenas o snapshot técnico da execução mais recente por usina.
7. Locks abandonados serão recuperados somente mediante timeout configurável e regra explícita, a ser concluída nesta PR.

## Consequências

- execuções passam a ser auditáveis de ponta a ponta;
- concorrência duplicada continua bloqueada;
- falhas podem ser retentadas sem persistir conteúdo sensível;
- endpoints e schedulers poderão compartilhar o mesmo runtime;
- métricas de duração ficam disponíveis para observabilidade e SLO.

## Segurança

Nenhuma credencial, identificador bruto de destino, coordenada, fatura ou resposta de provedor é registrada no ledger ou nos logs estruturados.