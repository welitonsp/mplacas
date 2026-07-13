# ADR-024 — Remediação da auditoria: explicações e coleta climática

## Status

Aceito.

## Contexto

A auditoria das PRs nº 1 a nº 27 identificou duas dívidas técnicas reais: a PR nº 17 havia criado somente os contratos e o fallback das explicações assistidas por IA, e a PR nº 24 não possuía cobertura específica do endpoint climático nem métricas próprias de persistência.

## Decisão

1. As explicações operacionais são construídas exclusivamente a partir do dashboard executivo e de seus diagnósticos determinísticos.
2. O adaptador de IA é um gateway HTTP configurável por ambiente, com resposta JSON estruturada.
3. O gateway recebe somente assunto técnico, status, manchete e evidências normalizadas; nunca recebe fatura, CPF, endereço, coordenadas, credenciais ou payloads externos.
4. A ausência ou falha do gateway não impede a resposta: o serviço retorna o fallback determinístico já existente.
5. O disclaimer final é definido pela aplicação e não pode ser substituído pelo provedor.
6. O endpoint `GET /energy/explanations/latest` exige autenticação operacional.
7. A coleta climática registra métricas sanitizadas de recebidos, inseridos, atualizados e inalterados.
8. Falhas do provedor climático retornam mensagem pública genérica e registram somente código técnico e identificadores operacionais.
9. Testes usam `MockTransport`, dados sintéticos e nenhuma chamada real à internet.
10. O README passa a refletir a arquitetura e os endpoints realmente existentes.

## Consequências

- a camada de explicação deixa de ser apenas uma fundação e torna-se operacional;
- o sistema permanece funcional sem IA;
- o provedor pode ser substituído sem alterar os motores de negócio;
- a coleta climática passa a ter cobertura de endpoint e observabilidade mínima;
- as pendências identificadas na auditoria ficam encerradas antes de novas funcionalidades.

## Segurança

Tokens e chaves permanecem em secrets. Nenhuma informação pessoal ou payload bruto é enviado ao gateway de explicações, persistido no banco ou registrado nos logs.
