# ADR-017 — Ledger SQL de alertas e job de despacho

## Status

Aceito.

## Contexto

A fundação de alertas e o runtime Telegram precisam de deduplicação durável. Um conjunto em memória não protege contra reinício do processo, múltiplas instâncias ou reexecução agendada.

## Decisão

1. Persistir somente entregas confirmadas em `alert_delivery_records`.
2. Usar `fingerprint` único como chave de idempotência.
3. Registrar provedor, referência sanitizada do destino e horário de confirmação.
4. Tratar conflito de unicidade como entrega já registrada.
5. Executar lotes finitos por `run_alert_dispatch_job`.
6. Retornar contagens explícitas de avaliados, enviados, ignorados e falhos.
7. Manter a política de severidade e o envio desacoplados do job.

## Consequências

- Reinícios não provocam reenvio do mesmo alerta confirmado.
- Falhas do provedor não são registradas como sucesso e podem ser tentadas novamente.
- O resumo do job pode alimentar métricas e observabilidade.
- A criação da tabela deve ser acompanhada por migração Alembic antes da implantação produtiva.

## Segurança

Nenhum token, chat real, conteúdo bruto de fatura ou payload privado é persistido. `destination_ref` deve conter apenas uma referência operacional sanitizada.
