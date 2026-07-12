# ADR-015 — Entrega confiável de alertas pelo Telegram

## Contexto

O Mplacas já calcula diagnósticos energéticos e anomalias de forma determinística. A próxima etapa é notificar o usuário sem transformar o canal de mensagens em uma nova fonte de decisão, duplicidade ou exposição de dados sensíveis.

## Decisão

A camada de alertas deve:

- receber apenas eventos previamente classificados;
- respeitar severidade mínima configurável;
- usar uma impressão digital estável para deduplicação;
- registrar envio somente após confirmação do provedor;
- permitir nova tentativa quando a entrega falhar;
- não alterar severidade, evidência ou recomendação;
- enviar somente texto sanitizado;
- manter o provedor Telegram atrás de um contrato substituível.

## Consequências

- alertas informativos podem ser suprimidos sem perder diagnósticos persistidos;
- falhas do Telegram não marcam o evento como entregue;
- o mesmo evento não é reenviado indefinidamente;
- a regra de negócio continua fora do provedor de mensagens.

## Fora de escopo desta fundação

- persistência definitiva do ledger de entregas;
- adaptador HTTP real do Bot API;
- agendamento automático;
- preferências por usuário;
- escalonamento entre canais.
