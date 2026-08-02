# ADR-063 — Cloud Monitoring e watchdog operacional

## Status

Aceito em 2026-08-02.

## Contexto

Alertas baseados somente em telemetria emitida pela aplicação não distinguem saúde real de silêncio:
um Scheduler pausado, IAM quebrado ou job nunca iniciado deixa de produzir tanto a métrica de sucesso
quanto a de falha. Além disso, políticas criadas manualmente não têm revisão, identidade estável nem
reconciliação segura.

## Decisão

Usar a métrica nativa de execuções concluídas dos Cloud Run Jobs em duas políticas versionadas:

- limiar imediato para resultado diferente de `succeeded` em todos os jobs obrigatórios;
- ausência por duas horas de sucesso do job horário `operational-watchdog`.

O watchdog consulta o ledger do pipeline e falha quando não há histórico saudável dentro do contrato
de 26 horas ou quando detecta falha/stuck. A busca da planta é somente leitura e não reutiliza o fluxo
que cria plantas automaticamente.

O provisionador identifica políticas por `userLabels.mplacas_policy_id`, rejeita duplicatas e usa
create/update estáveis. O verificador exige Scheduler `ENABLED`, política habilitada, canal configurado
e executa o watchdog para inicializar a série temporal.

## Consequências

Uma interrupção silenciosa passa a ser observável sem depender do processo que falhou. As políticas
são revisáveis e idempotentes. Em contrapartida, o ambiente precisa fornecer ao menos um canal válido,
a primeira amostra bem-sucedida é necessária e mudanças na semântica da métrica nativa exigem revisão
dos filtros versionados.
