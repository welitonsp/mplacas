# operational-watchdog-absence-drill.json — nota de sincronização manual

Este arquivo é um fork controlado de `operational-watchdog-absence.json`, criado exclusivamente para o
ensaio (drill) do incidente de ausência descrito em `docs/RUNBOOK_WATCHDOG_DRILL.md`. JSON não suporta
comentários nativos — este `.md` ao lado é o lugar combinado para registrar o vínculo.

**`operational-watchdog-absence.json` é a fonte da verdade da configuração real de produção.**
Este fork NUNCA deve divergir dela nos seguintes campos — qualquer mudança no original precisa ser
replicada aqui manualmente, e vice-versa nunca:

- `alertStrategy.autoClose` (janela de fechamento automático do incidente);
- `conditions[0].conditionAbsent.duration` (janela de ausência, hoje `7200s` / 2 horas);
- `conditions[0].conditionAbsent.aggregations[0].alignmentPeriod` (hoje `3600s`);
- `conditions[0].conditionAbsent.aggregations[0].perSeriesAligner` (hoje `ALIGN_DELTA`);
- `conditions[0].conditionAbsent.aggregations[0].crossSeriesReducer` (hoje `REDUCE_SUM`);
- `conditions[0].conditionAbsent.trigger.count` (hoje `1`);
- a métrica monitorada (`metric.type` e `metric.labels.result`).

As únicas diferenças intencionais e permanentes em relação ao original são:

- `resource.labels.job_name` aponta para `${GCP_OPERATIONAL_JOB_PREFIX}-watchdog-drill`
  (`mplacas-watchdog-drill`) em vez de `${GCP_OPERATIONAL_JOB_PREFIX}-operational-watchdog`;
- `displayName` e o texto de `documentation.content` são prefixados com `[DRILL]` e deixam explícito
  que é um ensaio, não um incidente real do watchdog de produção;
- `userLabels.mplacas_policy_id` é `operational_watchdog_absence_drill` (sufixo `_drill`), para que
  `upsert_monitoring_policy`/`find_monitoring_policy` em `infra/gcp/lib.sh` nunca colidam com a policy
  real `operational_watchdog_absence`.

Este fork é provisionado por `infra/gcp/drill/provision-watchdog-drill.sh` e removido por
`infra/gcp/drill/teardown-watchdog-drill.sh`. Ambos os scripts só rodam contra o projeto GCP real
(`mplacas`), de propósito — ver o comentário de topo de cada script.
