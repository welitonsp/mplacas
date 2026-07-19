# ADR-041 - Observabilidade estruturada e correlação com Cloud Trace

## Status

Aceito.

## Contexto

O Mplacas já gerava e preservava `X-Request-ID`, registrava a duração das requisições e mantinha um
ledger do pipeline diário. Ainda faltava um contexto propagado para logs internos, correlação nativa
entre Cloud Logging e Cloud Trace, spans para FastAPI, SQLAlchemy e HTTPX, e duração por etapa do
pipeline. Incidentes ainda exigiam reconstrução manual entre logs independentes.

## Decisão

1. Produção escreve um objeto JSON por linha em stdout, com timestamp, severidade, serviço, logger e
   campos estruturados.
2. O middleware aceita `X-Cloud-Trace-Context` e `traceparent` estritamente validados, gera contexto
   quando nenhum é fornecido e devolve `X-Trace-ID` junto do `X-Request-ID` existente.
3. Todos os logs emitidos dentro da requisição ou job recebem o contexto por `ContextVar`.
4. Os campos especiais `logging.googleapis.com/trace`, `spanId` e `trace_sampled` conectam logs aos
   spans no console do Google Cloud.
5. OpenTelemetry instrumenta FastAPI, SQLAlchemy e HTTPX quando
   `MPLACAS_CLOUD_TRACE_ENABLED=true`, usando amostragem parent-based configurável.
6. O pipeline diário registra início, fim, falha, duração e contadores para aquisição do lock,
   coleta climática, alertas e finalização.
7. URLs HTTP em spans nunca incluem query string. O token presente no path da API do Telegram é
   substituído por `<redacted>` antes da exportação.
8. O bootstrap concede apenas `roles/cloudtrace.agent` à identidade de runtime e habilita a API do
   Cloud Trace.

## Consequências

### Positivas

- Uma requisição ou job pode ser seguido de ponta a ponta por trace ID.
- Logs do Cloud Run são consultáveis por campos sem infraestrutura adicional.
- Etapas lentas ou travadas do pipeline ficam identificáveis por duração e resultado.
- Dependências externas e banco passam a aparecer na mesma árvore de spans.

### Negativas

- As dependências OpenTelemetry aumentam o tamanho da imagem e o tempo de instalação.
- A exportação exige a API Cloud Trace, credencial ADC e permissão `cloudtrace.agent`.
- A amostragem significa que nem todo trace bem-sucedido será exportado; logs continuam completos.

## Configuração

- `MPLACAS_GCP_PROJECT_ID`: projeto que recebe os spans e qualifica os campos de correlação.
- `MPLACAS_CLOUD_TRACE_ENABLED`: habilita SDK, instrumentações e exporter.
- `MPLACAS_TRACE_SAMPLE_RATE`: proporção de traces-raiz amostrados, entre 0 e 1; padrão `0.1`.

## Validação

- parsing estrito dos dois formatos de propagação;
- propagação e reset de contexto concorrente;
- JSON e campos especiais do Cloud Logging;
- remoção de query string e token do Telegram;
- logs de duração e contadores por operação;
- contratos de IAM, API e variáveis de deployment;
- Ruff, Mypy, Pytest, ShellCheck e smoke test do contêiner.
