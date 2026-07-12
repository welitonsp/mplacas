# ADR-010 — Tendências históricas por ciclos confirmados

## Status

Aceito.

## Contexto

O Mplacas precisa comparar a evolução energética entre ciclos sem atribuir causas que os dados não comprovam. A comparação deve ser reproduzível, auditável e compatível com múltiplas usinas.

## Decisão

- somente faturas em `CONFIRMED` participam da comparação;
- são usados os dois ciclos confirmados mais recentes, ordenados pelo fim do ciclo;
- cada ciclo é recalculado a partir da produção diária persistida da usina;
- a comparação usa indicadores consolidados, nunca texto bruto de fatura;
- produção, consumo total e energia importada possuem variação absoluta, percentual e direção;
- autossuficiência é comparada em pontos percentuais;
- o índice de saúde é comparado por diferença inteira;
- uma tolerância configurável define quando a variação é `STABLE`;
- quando a base anterior é zero, nenhum percentual artificial é produzido;
- diagnósticos históricos são determinísticos e não atribuem causalidade sem evidência;
- cálculos usam `Decimal` e o endpoint exige autenticação operacional.

## Consequências

A API passa a fornecer uma visão histórica explicável e segura para dashboards, relatórios e futuras explicações assistidas por IA. A IA poderá narrar resultados, mas não substituirá os cálculos nem a classificação de tendência.
