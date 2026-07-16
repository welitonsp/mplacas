# Checkpoint do projeto - 16/07/2026

## Estado atual

- Branch auditada e atualizada: `main`.
- Ultimo commit integrado antes desta fase: `f1df195` - PR no 37, auditoria persistente ampliada
  para mutacoes administrativas.
- PRs no 1 a no 28: encerradas sem pendencias conhecidas pela auditoria de rastreabilidade.
- PR no 29: auditoria documental das PRs 1 a 28.
- PR no 31: preparacao para Cloud Run.
- PR no 32: automacao segura de implantacao no Google Cloud.
- PR no 33: relatorio mensal auditavel e CSV.
- PR no 34: exportacoes PDF e XLSX.
- PR no 35: endurecimento operacional apos auditoria tecnica profunda.
- PR no 36: auditoria persistente inicial de acoes sensiveis.
- PR no 37: auditoria persistente ampliada para mutacoes administrativas.

O checkpoint antigo de 12/07/2026 indicava retomada na PR no 21, mas esse plano ja foi executado e
superado. A fonte de continuidade e a auditoria tecnica profunda de 16/07/2026, acompanhada pelas
ADRs 029 a 035.

## Fases recentes

### Remediacao P0 da auditoria tecnica profunda

1. proteger `/operations/jobs` e `/operations/status` com chave operacional;
2. preservar o ledger de falha do Cloud Run Job diario por commit em excecao;
3. adicionar indices operacionais para consultas por usina/ciclo;
4. documentar a decisao no ADR-029;
5. adicionar testes de contrato para os pontos criticos.

### Egress, request ID e rastreabilidade HTTP

1. validar allowlist de URLs externas em producao;
2. adicionar `X-Request-ID` e logging HTTP sem payload, query string ou segredos;
3. documentar a decisao no ADR-030;
4. adicionar testes de configuracao e rastreabilidade de requisicao.

### Autorizacao operacional por papel

1. adicionar `OperationsPrincipal` com papeis `ADMIN` e `READ`;
2. manter `MPLACAS_OPERATIONS_API_KEY` como credencial administrativa compativel;
3. adicionar `MPLACAS_OPERATIONS_READ_API_KEY` opcional para consumidores somente leitura;
4. aplicar o papel de leitura em operacoes, energia, explicacoes e relatorios;
5. documentar a decisao no ADR-031.

### Trilha auditavel de credencial operacional

1. adicionar `credential_id` estavel e nao reversivel ao `OperationsPrincipal`;
2. registrar `operations_role` e `operations_credential_id` no log HTTP autenticado;
3. manter segredo bruto fora de logs, respostas e persistencia;
4. documentar a decisao no ADR-032.

### Auditoria persistente inicial

1. criar tabela `audit_events`;
2. registrar eventos de confirmacao/rejeicao de faturas;
3. registrar sucesso/falha operacional de execucao de pipeline;
4. manter detalhes sem payloads privados ou segredos;
5. documentar a decisao no ADR-033.

### Auditoria persistente ampliada

1. registrar `billing.intake_text` ao criar fatura pendente;
2. registrar `climate.collect` ao persistir observacoes climaticas;
3. registrar `alerts.run` ao executar alertas administrativos;
4. manter detalhes apenas com IDs, datas, status e contadores;
5. documentar a decisao no ADR-034.

### Escopo obrigatorio de faturas por usina

1. tornar `utility_bills.plant_id` obrigatorio no modelo e na migration;
2. fazer backfill automatico apenas quando existe exatamente uma planta;
3. remover atalhos de fatura legada dos servicos de inteligencia;
4. exigir `plant_id` resolvido nos repositorios e fluxos de intake;
5. documentar a decisao no ADR-035.

## Proximas melhorias ainda abertas

1. Evoluir de API keys para usuarios/tenants/claims e escopo por `plant_id`.
2. Refatorar relatorios em modulos menores depois que a superficie operacional estiver estavel.
3. Adicionar metricas OpenTelemetry/Prometheus e alertas de SLO.

## Regra de retomada

Antes de abrir nova funcionalidade, manter:

- Ruff verde;
- Mypy verde;
- Pytest verde;
- documentacao da decisao atualizada;
- nenhuma pendencia P0 aberta dentro do escopo da PR em andamento.
