# ADR-042 - Métricas OpenTelemetry e alertas de SLO no Cloud Monitoring

## Status

**Parcialmente substituído por ADR-076 em 2026-08-26.** Continua valendo: os instrumentos
OpenTelemetry e a disciplina de cardinalidade baixa (`operation`, `outcome`).

Deixou de valer: o exportador Cloud Monitoring e as políticas de alerta de SLO, que viviam em
`infra/gcp/monitoring/` e foram removidas com a saída do Google Cloud. **O projeto está sem
alerta operacional externo** — ver ADR-076 § *Riscos aceitos*.

## Contexto

O ADR-041 estabeleceu logs estruturados, propagação de contexto e spans no Cloud Trace. A auditoria
técnica profunda de 16/07/2026 classificou como P1 a adição de métricas OpenTelemetry e alertas de
SLO. Sem métricas agregadas, falhas recorrentes do pipeline diário, do despacho de alertas ou da
coleta climática só apareciam por inspeção de logs ou traces amostrados, sem alertas automáticos.

## Decisão

1. Um `MeterProvider` OpenTelemetry é configurado junto do tracing em `configure_observability`,
   controlado por `MPLACAS_CLOUD_METRICS_ENABLED` e exportando pelo
   `CloudMonitoringMetricsExporter` no intervalo `MPLACAS_METRICS_EXPORT_INTERVAL_SECONDS`
   (padrão 60 s, validado entre 10 e 3600).
2. `observe_operation` passa a registrar duas métricas para toda operação observada:
   - `mplacas.operation.duration` (histograma, ms);
   - `mplacas.operation.runs` (contador).
3. Os atributos das métricas ficam restritos a `operation` e `outcome`
   (`success`/`failure`). Campos como `plant_id` e datas permanecem apenas em logs e spans, para
   manter a cardinalidade das séries temporais limitada e o custo previsível.
4. Com métricas desabilitadas, o registro é no-op: nenhuma dependência de rede, nenhuma falha.
5. Habilitar métricas exige `MPLACAS_GCP_PROJECT_ID`, espelhando a regra do Cloud Trace
   (falha fechada na configuração).
6. O bootstrap habilita `monitoring.googleapis.com` e concede apenas
   `roles/monitoring.metricWriter` à identidade de runtime.
7. As políticas de alerta de SLO são criadas por comandos documentados no
   `RUNBOOK_SLO_ALERTS.md`, fora do caminho de deploy, para manter o deploy idempotente e as
   políticas auditáveis.

## Consequências

### Positivas

- Falhas do pipeline diário, do outbox de alertas e da coleta climática geram séries temporais
  consultáveis e alertáveis sem depender de leitura de logs.
- Latência por operação fica disponível como distribuição (p50/p95/p99) no Metrics Explorer.
- O mesmo ponto de instrumentação (`observe_operation`) alimenta logs, spans e métricas, sem
  duplicação de código nos serviços.

### Negativas

- O exporter `opentelemetry-exporter-gcp-monitoring` é distribuído apenas em canal alpha
  (`1.12.0a0`); o adaptador permanece isolado em `observability/metrics.py` para conter mudanças.
- Métricas customizadas no Cloud Monitoring têm custo por série; a restrição de atributos é a
  salvaguarda principal.
- O intervalo de exportação introduz atraso de até um intervalo na visibilidade dos pontos.

## Configuração

- `MPLACAS_CLOUD_METRICS_ENABLED`: habilita provider e exportação; padrão `false`.
- `MPLACAS_METRICS_EXPORT_INTERVAL_SECONDS`: intervalo de exportação; padrão `60`.
- `MPLACAS_GCP_PROJECT_ID`: obrigatório quando métricas estão habilitadas.

## Validação

- histograma e contador emitidos com atributos corretos em sucesso e falha;
- duração negativa saturada em zero;
- atributos limitados a `operation` e `outcome` mesmo quando a operação carrega campos extras;
- modo desabilitado permanece no-op sem exceções;
- configuração exige projeto e intervalo válido;
- contratos de deployment cobrem API, papel IAM e variável de ambiente.
