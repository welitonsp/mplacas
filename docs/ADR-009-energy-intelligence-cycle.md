# ADR-009 — Inteligência energética por ciclo confirmado

## Status

Aceito.

## Contexto

O Mplacas precisa combinar a produção diária persistida da NEPViewer com faturas da Equatorial sem transformar dados incompletos em valores confiáveis e sem delegar cálculos a IA generativa.

## Decisão

- somente faturas em `CONFIRMED` podem alimentar o resumo energético;
- a produção é somada no intervalo inclusivo do ciclo de leitura;
- dados de todos os dispositivos vinculados à usina são agregados por data;
- dias sem registro são contabilizados como ausentes, nunca convertidos silenciosamente em zero;
- dias `PROVISIONAL`, `INCOMPLETE` e `UNAVAILABLE` são expostos separadamente;
- dados incompletos e indisponíveis penalizam a qualidade do ciclo;
- todos os cálculos energéticos e financeiros usam `Decimal`;
- o endpoint é protegido pela mesma credencial operacional dos demais endpoints administrativos;
- a API retorna indicadores e diagnósticos auditáveis, mas não expõe conteúdo bruto de faturas, credenciais ou dados pessoais.

## Consequências

O resultado é reproduzível, explicável e independente de IA. A qualidade dos dados permanece visível para impedir consolidações enganosas. A associação entre fatura e usina é explícita por `plant_id`, preparando o sistema para múltiplas usinas.
