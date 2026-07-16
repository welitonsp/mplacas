# ADR-031 - Papel operacional somente leitura por API key

## Status

Aceito.

## Contexto

A auditoria técnica profunda identificou que uma única chave operacional para todas as ações não é
suficiente para a evolução do Mplacas como plataforma SaaS/multiusina. Implementar usuários,
tenants, RBAC completo e trilha de ator exigirá uma fase maior, mas o sistema já pode reduzir risco
separando credenciais de leitura de credenciais administrativas.

Os endpoints de leitura de energia, relatórios, explicações e status operacional precisam ser
consumidos por dashboards, operadores e integrações sem entregar a mesma chave que executa pipeline,
coleta climática, alerta ou alteração de faturas.

## Decisão

1. Manter `MPLACAS_OPERATIONS_API_KEY` como credencial administrativa e compatível com o
   comportamento existente.
2. Adicionar `MPLACAS_OPERATIONS_READ_API_KEY` como credencial opcional somente leitura.
3. Modelar a autenticação como `OperationsPrincipal` com papéis:
   - `ADMIN`;
   - `READ`.
4. Criar uma dependência `require_operations_read` que aceita `ADMIN` ou `READ`.
5. Manter `require_operations_key` como dependência administrativa, aceitando apenas `ADMIN`.
6. Aplicar `READ` aos routers de leitura:
   - `/operations/*`;
   - `/energy/*`;
   - `/energy/explanations/*`;
   - `/reports/*`.
7. Manter endpoints de mutação/execução exigindo a chave administrativa:
   - billing;
   - Telegram webhook por segredo próprio;
   - clima;
   - alertas;
   - pipeline.

## Consequências

### Positivas

- Dashboards e integrações de consulta podem usar uma credencial menos poderosa.
- A aplicação passa a ter um conceito explícito de principal operacional.
- A migração futura para usuários, tenants, claims e auditoria de ator fica menos disruptiva.

### Negativas

- Ainda não há identidade nominal de usuário, tenant nem escopo por `plant_id`.
- A chave somente leitura ainda precisa ser tratada como segredo.
- Os scripts de Cloud Run continuam provisionando apenas os segredos obrigatórios; a chave de leitura
  é opcional e deve ser adicionada quando houver consumidor somente leitura.

## Validação

A entrega deve permanecer coberta por:

- testes de autenticação `ADMIN`;
- testes de autenticação `READ`;
- teste garantindo que `READ` não satisfaz dependência administrativa;
- teste de acesso a endpoint de leitura com `MPLACAS_OPERATIONS_READ_API_KEY`;
- Ruff;
- Mypy;
- Pytest.

