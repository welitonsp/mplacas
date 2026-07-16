# Checkpoint do projeto - 16/07/2026

## Estado atual

- Branch auditada e atualizada: `main`.
- Último commit integrado: `8a7e8fc` - PR nº 34, exportações PDF e XLSX auditáveis.
- PRs nº 1 a nº 28: encerradas sem pendências conhecidas pela auditoria de rastreabilidade.
- PR nº 29: auditoria documental das PRs 1 a 28.
- PR nº 31: preparação para Cloud Run.
- PR nº 32: automação segura de implantação no Google Cloud.
- PR nº 33: relatório mensal auditável e CSV.
- PR nº 34: exportações PDF e XLSX.

O checkpoint antigo de 12/07/2026 indicava retomada na PR nº 21, mas esse plano já foi executado e
superado. A nova fonte de continuidade é a auditoria técnica profunda de 16/07/2026.

## Nova retomada

A próxima linha de trabalho deve ser tratada como PR nº 35:

**Tema:** remediação P0 da auditoria técnica profunda.

Escopo implementado nesta retomada:

1. proteger `/operations/jobs` e `/operations/status` com a chave operacional;
2. preservar o ledger de falha do Cloud Run Job diário por commit em exceção;
3. adicionar índices operacionais para consultas por usina/ciclo;
4. documentar a decisão no ADR-029;
5. adicionar testes de contrato para os três pontos.

## Próximas melhorias após a PR nº 35

Escopo implementado na fase seguinte:

1. validar allowlist de URLs externas em produção;
2. adicionar `X-Request-ID` e logging HTTP sem payload, query string ou segredos;
3. documentar a decisão no ADR-030;
4. adicionar testes de configuração e rastreabilidade de requisição.

Próximas melhorias ainda abertas:

Escopo implementado na fase de autorização seguinte:

1. adicionar `OperationsPrincipal` com papéis `ADMIN` e `READ`;
2. manter `MPLACAS_OPERATIONS_API_KEY` como credencial administrativa compatível;
3. adicionar `MPLACAS_OPERATIONS_READ_API_KEY` opcional para consumidores somente leitura;
4. aplicar o papel de leitura em operações, energia, explicações e relatórios;
5. documentar a decisão no ADR-031.

Próximas melhorias ainda abertas:

Escopo implementado na fase de trilha operacional:

1. adicionar `credential_id` estável e não reversível ao `OperationsPrincipal`;
2. registrar `operations_role` e `operations_credential_id` no log HTTP autenticado;
3. manter segredo bruto fora de logs, respostas e persistência;
4. documentar a decisão no ADR-032.

Próximas melhorias ainda abertas:

1. Evoluir de API keys para usuários/tenants/claims e escopo por `plant_id`.
2. Criar auditoria persistente de ações de negócio sensíveis.
3. Migrar faturas legadas para `plant_id` obrigatório.
4. Refatorar relatórios em módulos menores depois que a superfície operacional estiver estável.
5. Adicionar métricas OpenTelemetry/Prometheus e alertas de SLO.

## Regra de retomada

Antes de abrir nova funcionalidade, manter:

- Ruff verde;
- Mypy verde;
- Pytest verde;
- documentação da decisão atualizada;
- nenhuma pendência P0 aberta dentro do escopo da PR em andamento.
