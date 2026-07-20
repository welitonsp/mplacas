# Runbook - Alertas de SLO no Google Cloud Monitoring

Este runbook cria as políticas de alerta sobre as métricas definidas no ADR-042. Execute no Google
Cloud Shell, no mesmo projeto do deploy. As políticas são criadas uma única vez e permanecem fora do
caminho de deploy.

As métricas customizadas OpenTelemetry aparecem no Cloud Monitoring com o prefixo
`workload.googleapis.com/`:

- `workload.googleapis.com/mplacas.operation.runs`
- `workload.googleapis.com/mplacas.operation.duration`

## Pré-requisitos

```bash
export GCP_PROJECT_ID="<seu-projeto>"
gcloud config set project "$GCP_PROJECT_ID"
```

Crie um canal de notificação por e-mail e guarde o nome completo retornado:

```bash
gcloud beta monitoring channels create \
  --display-name="Mplacas Operações" \
  --type=email \
  --channel-labels=email_address="<seu-email>"

gcloud beta monitoring channels list --format="value(name,displayName)"
export CHANNEL="projects/$GCP_PROJECT_ID/notificationChannels/<id>"
```

## SLO 1 - Falha do pipeline diário

Qualquer execução com `outcome=failure` nas operações do pipeline dispara alerta.

```bash
cat > /tmp/mplacas-pipeline-failure.json <<'EOF'
{
  "displayName": "Mplacas - falha em operação do pipeline diário",
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "operation.runs failure > 0 (5 min)",
      "conditionThreshold": {
        "filter": "metric.type=\"workload.googleapis.com/mplacas.operation.runs\" AND metric.labels.outcome=\"failure\" AND metric.labels.operation=monitoring.regex.full_match(\"daily_pipeline\\\\..*\")",
        "aggregations": [
          {
            "alignmentPeriod": "300s",
            "perSeriesAligner": "ALIGN_DELTA",
            "crossSeriesReducer": "REDUCE_SUM"
          }
        ],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0,
        "duration": "0s",
        "trigger": { "count": 1 }
      }
    }
  ]
}
EOF
gcloud alpha monitoring policies create \
  --policy-from-file=/tmp/mplacas-pipeline-failure.json \
  --notification-channels="$CHANNEL"
```

## SLO 2 - Falhas no despacho de alertas

```bash
cat > /tmp/mplacas-alert-dispatch-failure.json <<'EOF'
{
  "displayName": "Mplacas - falha no despacho de alertas",
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "alert_dispatch failure > 0 (15 min)",
      "conditionThreshold": {
        "filter": "metric.type=\"workload.googleapis.com/mplacas.operation.runs\" AND metric.labels.outcome=\"failure\" AND metric.labels.operation=\"daily_pipeline.alert_dispatch\"",
        "aggregations": [
          {
            "alignmentPeriod": "900s",
            "perSeriesAligner": "ALIGN_DELTA",
            "crossSeriesReducer": "REDUCE_SUM"
          }
        ],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0,
        "duration": "0s",
        "trigger": { "count": 1 }
      }
    }
  ]
}
EOF
gcloud alpha monitoring policies create \
  --policy-from-file=/tmp/mplacas-alert-dispatch-failure.json \
  --notification-channels="$CHANNEL"
```

## SLO 3 - Latência p95 de operações

Alerta quando o p95 da duração de qualquer operação ultrapassa 60 segundos por 10 minutos.

```bash
cat > /tmp/mplacas-operation-latency.json <<'EOF'
{
  "displayName": "Mplacas - latência p95 de operação acima de 60s",
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "operation.duration p95 > 60000 ms",
      "conditionThreshold": {
        "filter": "metric.type=\"workload.googleapis.com/mplacas.operation.duration\"",
        "aggregations": [
          {
            "alignmentPeriod": "300s",
            "perSeriesAligner": "ALIGN_PERCENTILE_95",
            "crossSeriesReducer": "REDUCE_MAX",
            "groupByFields": ["metric.labels.operation"]
          }
        ],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 60000,
        "duration": "600s",
        "trigger": { "count": 1 }
      }
    }
  ]
}
EOF
gcloud alpha monitoring policies create \
  --policy-from-file=/tmp/mplacas-operation-latency.json \
  --notification-channels="$CHANNEL"
```

## Verificação

1. Liste as políticas criadas:

```bash
gcloud alpha monitoring policies list --format="value(name,displayName)"
```

2. Confirme no Metrics Explorer que as métricas `mplacas.operation.runs` e
   `mplacas.operation.duration` recebem pontos após uma execução do pipeline com
   `MPLACAS_CLOUD_METRICS_ENABLED=true`.

3. Para testar o alerta de falha sem afetar produção, execute o job diário com uma configuração
   propositalmente inválida em ambiente de homologação e aguarde o intervalo de exportação.

## Remoção

```bash
gcloud alpha monitoring policies delete <policy-name> --quiet
```
