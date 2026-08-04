# Runbook — ensaio (drill) do incidente de ausência do watchdog operacional

## Objetivo

Provar, dentro do projeto GCP real de produção (`mplacas`), que a ausência de execução do watchdog
horário realmente abre um incidente no Cloud Monitoring e entrega uma notificação real no canal de
plantão configurado — e que retomar a execução realmente fecha esse incidente. Isso nunca foi
demonstrado; só implementado (`docs/CHECKLIST_REMEDIACAO_AUDITORIA.md`, item P1-05).

O ensaio usa um "gêmeo" isolado do watchdog real — job, agenda e policy próprios, todos com sufixo/prefixo
`-drill`/`_drill` — para que o drill fique coberto pelo guardrail de custo automatizado
(`infra/gcp/audit-costs.sh`) e produza entrega no canal REAL de produção, sem tocar em nenhum recurso do
watchdog de produção de verdade (`mplacas-operational-watchdog` / policy `operational_watchdog_absence`).
Ver `infra/gcp/monitoring/operational-watchdog-absence-drill.md` para o detalhamento do fork.

## Avisos importantes — leia antes de começar

- **Isto gera um e-mail de incidente REAL** no(s) canal(is) de notificação configurado(s) em
  `GCP_MONITORING_NOTIFICATION_CHANNELS` — o mesmo canal de plantão da produção real. Isso é intencional
  e foi aceito pelo usuário como parte da prova; avise a equipe de plantão antes de iniciar para evitar
  confusão com um incidente real.
- `infra/gcp/lib.sh` recebeu uma entrada temporária (`mplacas-watchdog-drill`) em
  `MPLACAS_EXPECTED_SCHEDULER_JOBS` para que `audit-costs.sh` não trate o Scheduler do drill como recurso
  proibido. **Essa entrada precisa ser removida manualmente** depois do decomissionamento (ver passo
  final abaixo) — não é revertida automaticamente.
- `provision-watchdog-drill.sh` e `teardown-watchdog-drill.sh` só rodam contra o projeto real `mplacas`
  (o oposto do padrão de guardrail dos demais scripts do repositório, que bloqueiam produção). Isso é
  proposital: o ponto do drill é provar entrega no canal real, o que só é possível no projeto real.

## Pré-requisitos

- `infra/gcp/config.env` com `GCP_PROJECT_ID=mplacas`, `GCP_REGION=us-central1` e
  `GCP_MONITORING_NOTIFICATION_CHANNELS` já apontando para o(s) canal(is) real(is) de produção.
- O watchdog real (`mplacas-operational-watchdog`) já provisionado e saudável
  (`infra/gcp/verify-operations.sh`), para que ninguém confunda o incidente do drill com um evento real.

## Provisionamento

```bash
bash infra/gcp/drill/provision-watchdog-drill.sh
```

Cria/atualiza, de forma idempotente, dentro do projeto `mplacas`:

- Cloud Run Job `mplacas-watchdog-drill` (imagem pública mínima `busybox:stable`, pinada por digest,
  comando `sh -c "exit 0"`, sem secrets, sem variáveis de negócio);
- Cloud Scheduler `mplacas-watchdog-drill`, mesma cadência horária do watchdog real (`5 * * * *`);
- policy `operational_watchdog_absence_drill`
  (`infra/gcp/monitoring/operational-watchdog-absence-drill.json`), usando o MESMO canal de notificação
  já configurado para produção — nenhum canal novo é criado.

Exige confirmação exata (`PROVISION-WATCHDOG-DRILL-mplacas`) antes de criar qualquer recurso.

Depois de provisionar, deixe pelo menos uma execução bem-sucedida do Scheduler acontecer (até 1h) para
que a série temporal `run.googleapis.com/job/completed_execution_count{result=succeeded}` do job
`mplacas-watchdog-drill` tenha ao menos uma amostra — a condição de ausência só pode abrir incidente
depois disso, exatamente como no watchdog real (ver `docs/RUNBOOK_SLO_ALERTS.md`).

## Sequência do ensaio (T0 → T3)

### T0 — pausar a agenda do drill

```bash
gcloud scheduler jobs pause mplacas-watchdog-drill \
  --location us-central1 \
  --project mplacas
```

Confirme o estado:

```bash
gcloud scheduler jobs describe mplacas-watchdog-drill \
  --location us-central1 \
  --project mplacas \
  --format='value(state)'
# esperado: PAUSED
```

Registre o horário exato de T0.

### Aguardar a janela mínima (T0 + 3h)

A policy do drill é uma cópia fiel da policy real
(`infra/gcp/monitoring/operational-watchdog-absence.json`) nos parâmetros de tempo:

- `conditions[0].conditionAbsent.duration`: `7200s` (2h) — janela de ausência exigida pela condição;
- `conditions[0].conditionAbsent.aggregations[0].alignmentPeriod`: `3600s` (1h) — período de
  alinhamento (`ALIGN_DELTA`) da série temporal.

Na prática o Cloud Monitoring só fecha o primeiro período de alinhamento depois de decorrida uma hora,
e só então começa a contar as 2 horas de ausência — por isso a janela mínima segura para esperar
abertura do incidente é **T0 + 3h** (`7200s` + `3600s`). Não confirme ausência de incidente antes disso.

### T1 — confirmar abertura do incidente

**Correção de processo (2026-08-04, drill real executado):** a checagem original abaixo, via log de
auditoria filtrando `protoPayload.methodName:"CreateAlert"`, **não funciona** — não existe esse tipo de
evento de auditoria para criação de incidente do Cloud Monitoring, e a API `v3` do Monitoring não expõe
um recurso `incidents` publicamente (`gcloud alpha monitoring` também não tem esse comando). No drill
real, o `gcloud logging read` com esse filtro nunca retornou nada mesmo com o incidente tendo aberto de
verdade e o e-mail real tendo sido entregue — **não trate essa ausência de log como falha do drill.**

O critério de aceite real e único confiável é **o e-mail (ou canal configurado) de notificação
recebido de fato** — confirme isso diretamente na caixa de entrada, fora do `gcloud`. Opcionalmente,
para corroborar que a condição de ausência é real (não prova o incidente em si, só a métrica
subjacente), consulte a série temporal bruta:

```bash
TOKEN=$(gcloud auth print-access-token)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://monitoring.googleapis.com/v3/projects/mplacas/timeSeries?filter=metric.type%3D%22run.googleapis.com%2Fjob%2Fcompleted_execution_count%22%20AND%20resource.labels.job_name%3D%22mplacas-watchdog-drill%22&interval.startTime=<T0 em RFC3339>&interval.endTime=<agora em RFC3339>&view=FULL"
```

Ausência de pontos novos depois de T0 confirma que a condição de ausência é real; não confirma, por si
só, que o incidente abriu — só o e-mail confirma isso.

Registre o horário exato de T1 (e-mail recebido, conforme relatado pelo operador).

### T2 — retomar e forçar uma execução imediata

```bash
gcloud scheduler jobs resume mplacas-watchdog-drill \
  --location us-central1 \
  --project mplacas

gcloud run jobs execute mplacas-watchdog-drill \
  --region us-central1 \
  --project mplacas \
  --wait
```

Registre o horário exato de T2.

### Aguardar T2 + 1h30 e confirmar fechamento (T3)

O `alertStrategy.autoClose` da policy é `604800s` (7 dias) — isso é apenas o limite de auto-close por
inatividade, não o tempo de fechamento esperado quando a condição volta a ser satisfeita. Com a série
temporal voltando a registrar sucesso a cada hora, o Cloud Monitoring reavalia a condição no próximo
período de alinhamento (até 1h) e fecha o incidente automaticamente quando a ausência deixa de ser
verdadeira; aguarde **T2 + 1h30** como margem de segurança antes de declarar falha caso ainda esteja
aberto.

Mesma correção de processo do T1: não há checagem de `gcloud` que confirme diretamente o fechamento do
incidente. Confirme via **e-mail de fechamento** (se o canal notificar fechamento) ou, na ausência
disso, pela série temporal voltando a registrar sucesso (comando de série temporal do T1, agora
apontando para depois de T2) como evidência indireta de que a condição deixou de ser verdadeira.

Registre o horário exato de T3 (fechamento confirmado).

## Decomissionamento (até 48h após o drill aprovado)

```bash
bash infra/gcp/drill/teardown-watchdog-drill.sh
```

Remove, dentro do projeto `mplacas`:

- o Cloud Scheduler `mplacas-watchdog-drill` (pausado antes de remover, para evitar corrida);
- o Cloud Run Job `mplacas-watchdog-drill`;
- a policy `operational_watchdog_absence_drill`.

O canal de notificação (real, de produção) nunca é tocado.

O script imprime, ao final, um lembrete: **remova manualmente a entrada temporária
`mplacas-watchdog-drill` de `MPLACAS_EXPECTED_SCHEDULER_JOBS` em `infra/gcp/lib.sh`**. Essa remoção não
é automática — editar um array bash via script é frágil, e deixar a entrada esquecida no repositório
tornaria o allowlist do `audit-costs.sh` permanentemente mais permissivo do que deveria.

## Evidência a registrar

Ao final do drill, anexe ao registro da mudança (sem copiar segredos ou connection strings):

- horários exatos de T0, T1, T2 e T3;
- ID do incidente aberto e fechado;
- confirmação de recebimento da notificação real (abertura e, se aplicável, fechamento);
- resultado do `teardown-watchdog-drill.sh` e a confirmação de que a entrada temporária foi removida de
  `infra/gcp/lib.sh`.

Depois disso, atualize `docs/CHECKLIST_REMEDIACAO_AUDITORIA.md` (item P1-05) de `[~]` para `[x]`.
