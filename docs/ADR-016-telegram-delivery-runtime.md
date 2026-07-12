# ADR-016 — Runtime de entrega de alertas pelo Telegram

## Contexto

A PR nº 18 definiu contratos, severidade, deduplicação e política de entrega. Faltava um adaptador concreto para a Telegram Bot API e uma abstração de ledger que permitisse deduplicação fora da memória do processo.

## Decisão

1. O adaptador `TelegramAlertProvider` usa `httpx` e recebe token, chat e timeout por configuração externa.
2. Nenhuma credencial é persistida ou registrada pelo módulo.
3. As mensagens são texto simples, curtas e compostas apenas por título, severidade, diagnóstico, ação recomendada e horário.
4. A entrega só é marcada no ledger depois de uma confirmação HTTP válida e de `ok=true` na resposta da API.
5. Falhas de rede ou do provedor não marcam o alerta como entregue, permitindo nova tentativa.
6. O runtime depende do contrato `AlertDeliveryLedger`, permitindo uma implementação persistente posterior sem alterar a regra de negócio.
7. A implementação em memória existe apenas para testes e desenvolvimento de processo único.

## Consequências

- o sistema passa a ter um adaptador Telegram real sem acoplar a política de alerta ao fornecedor;
- deduplicação e entrega permanecem testáveis sem rede;
- a próxima evolução deve implementar um ledger SQL transacional e um job agendado de avaliação;
- mensagens não incluem credenciais, faturas brutas, payloads da NEPViewer ou dados pessoais desnecessários.
