# ADR-013 — Motor climático e detecção determinística de anomalias

## Status

Aceito.

## Contexto

O Mplacas precisa distinguir variações compatíveis com baixa disponibilidade solar de quedas de produção que merecem investigação técnica. Essa classificação não pode depender de IA generativa nem transformar ausência de dados em evidência.

## Decisão

- usar um contrato `ClimateProvider` substituível;
- representar irradiação, nebulosidade e precipitação como dados opcionais e validados;
- manter produção esperada como entrada explícita, nunca inferida silenciosamente;
- calcular desvios com `Decimal`;
- classificar resultados em `NORMAL`, `ATTENTION`, `ANOMALY` e `CRITICAL`;
- tratar dados incompletos ou linha de base ausente como limitação de análise;
- não atribuir causa técnica somente pela existência de desvio;
- quando houver baixa irradiação, registrar contexto climático sem afirmar causalidade exclusiva;
- quando a queda não for acompanhada por baixa irradiação, recomendar investigação técnica sem declarar defeito;
- manter limiares configuráveis e ordenados;
- usar apenas dados sintéticos nos testes.

## Consequências

O motor permanece auditável, reproduzível e independente de IA generativa. Provedores meteorológicos podem ser trocados sem alterar a lógica de negócio. A qualidade e a ausência dos dados continuam visíveis no resultado.
