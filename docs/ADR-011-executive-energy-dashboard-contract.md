# ADR-011 — Contrato executivo de energia

## Status

Aceito.

## Contexto

O dashboard web e futuros canais de consulta precisam de uma resposta única e estável, sem reproduzir no cliente as regras de conciliação, qualidade, saúde e tendência já existentes no domínio.

## Decisão

- criar um serviço executivo que componha o ciclo confirmado mais recente e, quando disponível, a comparação com o ciclo anterior;
- manter cálculos, classificações e priorização no backend;
- expor o endpoint protegido `GET /energy/executive/latest?plant_id={plant_id}`;
- classificar o estado executivo como `HEALTHY`, `ATTENTION` ou `CRITICAL`;
- derivar a classificação somente de diagnósticos determinísticos e do índice de saúde;
- produzir uma manchete curta e uma lista deduplicada de até cinco ações prioritárias;
- aceitar que a tendência seja `null` quando houver apenas um ciclo confirmado;
- não transformar ausência de histórico em erro do dashboard atual;
- manter valores decimais serializados como texto para evitar perda de precisão no cliente;
- não expor conteúdo bruto de faturas, credenciais, identificadores pessoais ou payloads da NEPViewer.

## Consequências

O frontend recebe um contrato pronto para apresentação, com uma única chamada autenticada. As regras permanecem centralizadas, auditáveis e reutilizáveis por web, Telegram ou relatórios. O cliente não decide severidade nem recalcula indicadores financeiros ou energéticos.
