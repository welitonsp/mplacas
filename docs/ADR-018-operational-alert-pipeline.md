# ADR-018 — Pipeline operacional de alertas

## Status

Aceito.

## Contexto

As PRs nº 18 a nº 20 estabeleceram contratos, entrega pelo Telegram, deduplicação persistente e processamento em lote. Faltava conectar essas peças aos diagnósticos executivos e de anomalia, registrar a tabela por migração formal e oferecer uma execução operacional protegida.

## Decisão

1. Diagnósticos executivos e de anomalia são convertidos em `AlertCandidate` por funções determinísticas.
2. O fingerprint inclui somente identificadores técnicos e estado do diagnóstico, permitindo reexecução idempotente.
3. O endpoint `POST /alerts/run` exige a credencial operacional existente.
4. Token e destino do Telegram são lidos exclusivamente da configuração externa.
5. O destino persistido no ledger é uma referência derivada por hash, nunca o identificador bruto do chat.
6. O `SqlAlertDeliveryLedger` usa a mesma sessão assíncrona criada pelo `SessionFactory`.
7. A migração `20260713_0004` cria `alert_delivery_records` com fingerprint único.
8. Logs registram somente identificador da usina e contagens operacionais, sem token, chat, fatura ou payload externo.
9. Métricas mínimas: avaliados, enviados, ignorados, falhos, duplicados e abaixo da severidade mínima.
10. Falhas do provedor não são marcadas como entrega confirmada e permanecem elegíveis para nova tentativa.

## Consequências

- o pipeline completo pode ser executado por automação autenticada;
- reexecuções não reenviam alertas já confirmados;
- ausência de dados executivos ou climáticos não derruba todo o job;
- o Telegram continua sem autoridade sobre cálculo, severidade ou diagnóstico;
- a próxima evolução pode adicionar agendamento periódico e métricas exportáveis sem alterar a regra central.

## Segurança

Nenhuma credencial, identificador real de chat, fatura, endereço, unidade consumidora ou payload privado é persistido ou registrado. Os testes usam somente identificadores e valores sintéticos.
