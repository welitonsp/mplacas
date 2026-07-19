# ADR-030 - Validação de egress HTTP e rastreabilidade de requisições

## Status

Aceito.

## Contexto

Após a remediação P0 da auditoria técnica profunda, a próxima fase priorizada era reduzir risco de
configuração externa perigosa e melhorar diagnóstico de produção. O sistema já tinha timeouts e
adaptadores isolados para NEPViewer, Open-Meteo e gateway de explicações, mas produção ainda aceitava
qualquer host configurado por variável de ambiente. Também não havia um identificador estável para
correlacionar requisições HTTP com logs.

## Decisão

1. Em produção, URLs externas configuráveis precisam usar HTTPS.
2. Em produção, os hosts de `MPLACAS_NEP_BASE_URL`, `MPLACAS_CLIMATE_ARCHIVE_BASE_URL` e
   `MPLACAS_EXPLANATION_API_URL`, quando configurado, precisam existir em
   `MPLACAS_EXTERNAL_HTTP_ALLOWED_HOSTS`.
3. A allowlist padrão contém apenas `api.nepviewer.net` e `archive-api.open-meteo.com`.
4. Desenvolvimento e testes continuam flexíveis para facilitar mocks, ambientes locais e testes sem
   rede real.
5. Toda resposta HTTP recebe `X-Request-ID`.
6. Se o cliente enviar um `X-Request-ID` seguro, ele é preservado; valores vazios, longos ou com
   caracteres inseguros são substituídos por UUID gerado pela aplicação.
7. Cada requisição concluída registra log com `request_id`, método, path, status e duração em
   milissegundos, sem query string e sem payload.

## Consequências

### Positivas

- Reduz risco de SSRF/configuração acidental em produção.
- Torna troubleshooting de incidentes e suporte operacional mais simples.
- Mantém logs sem segredos, payloads, query strings ou cabeçalhos sensíveis.

### Negativas

- Qualquer gateway de explicações em produção exige atualização explícita da allowlist.
- Consumidores que já geravam IDs fora do formato seguro passarão a receber um novo ID gerado pela
  aplicação.

## Validação

A entrega deve permanecer coberta por:

- testes de rejeição de host fora da allowlist;
- testes de rejeição de URL não HTTPS em produção;
- teste de aceitação de host de explicações explicitamente autorizado;
- testes de geração, preservação e substituição de `X-Request-ID`;
- Ruff;
- Mypy;
- Pytest.

## Evolução

A correlação ponta a ponta, os logs JSON e a instrumentação OpenTelemetry foram adicionados pela
ADR-041. As regras deste ADR para `X-Request-ID`, ausência de query string e não exposição de
payloads continuam válidas.
