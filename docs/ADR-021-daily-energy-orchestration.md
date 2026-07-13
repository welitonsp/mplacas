# ADR-021 — Orquestração diária do pipeline energético

## Status

Aceito para implementação incremental na PR nº 25.

## Contexto

O Mplacas já possui coleta climática idempotente, análise determinística de anomalias, diagnóstico executivo e entrega de alertas com ledger SQL. Faltava uma unidade operacional única que encadeasse essas capacidades com fronteira transacional explícita.

## Decisão

1. A execução diária recebe `plant_id` e `target_date` explícitos.
2. A coleta climática ocorre antes da análise e do despacho de alertas.
3. Provedores climático e de alerta são injetados, preservando testabilidade.
4. A função de orquestração não executa `commit`; a fronteira transacional pertence ao endpoint, job ou scheduler chamador.
5. A idempotência continua sendo garantida pelos repositórios de clima e pelo ledger de alertas.
6. Valores esperados de produção devem ser positivos e o período de anomalias fica limitado a 1–90 dias.
7. Logs contêm somente identificadores técnicos, data e contagens operacionais.

## Consequências

- uma automação autenticada poderá executar o ciclo diário completo;
- reexecuções não duplicam clima nem alertas confirmados;
- falhas permanecem observáveis e não são mascaradas como sucesso;
- o scheduler poderá ser substituído sem alterar os motores determinísticos.

## Próximos blocos

- endpoint operacional protegido;
- ledger de execuções do pipeline;
- lock contra concorrência por usina e data;
- estados `RUNNING`, `SUCCEEDED` e `FAILED`;
- métricas de duração e falhas por etapa;
- testes de integração e CI integral.
