# ADR-029 - Endurecimento operacional após auditoria técnica profunda

## Status

Aceito.

## Contexto

A `main` foi atualizada até a PR nº 34, que adicionou exportações PDF e XLSX auditáveis. A auditoria
técnica profunda de 16/07/2026 identificou três riscos P0 que deveriam ser tratados antes de novas
funcionalidades:

1. `/operations/jobs` e `/operations/status` estavam expostos sem autenticação operacional.
2. O Cloud Run Job diário fazia rollback quando o pipeline falhava, apagando a atualização de
   ledger feita pelo runtime.
3. Consultas recorrentes por usina/ciclo não tinham todos os índices necessários para crescimento.

Esses riscos quebravam premissas anteriores dos ADRs de Cloud Run e observabilidade: o serviço pode
ser publicamente acessível apenas se os endpoints sensíveis estiverem protegidos, e falhas
operacionais precisam permanecer auditáveis.

## Decisão

1. Proteger todo o router `/operations` com `Depends(require_operations_key)`.
2. Manter `/health`, `/ready` e `/dashboard` públicos.
3. No Cloud Run Job diário, confirmar a transação também quando o runtime marca uma execução como
   falha e relança a exceção.
4. Adicionar migration para os índices:
   - `devices(plant_id)`;
   - `daily_energy_versions(daily_energy_id)`;
   - `utility_bills(plant_id, status, cycle_end, created_at)`.
5. Refletir os índices novos no metadata SQLAlchemy onde aplicável.
6. Cobrir as mudanças com testes de segurança, transação do job e contrato da migration.

## Consequências

### Positivas

- A superfície operacional volta a cumprir a premissa de autenticação própria da aplicação.
- Falhas de pipeline executadas por Cloud Run Job permanecem consultáveis no ledger.
- Consultas de dashboard, ciclos, histórico e relatórios ficam melhor preparadas para múltiplas
  usinas.

### Negativas

- Consumidores internos que chamavam `/operations/*` sem chave precisarão enviar `X-API-Key`.
- A migration precisa ser executada antes da próxima versão de produção.

## Validação

A entrega deve permanecer coberta por:

- teste de autenticação obrigatória em `/operations/jobs` e `/operations/status`;
- teste de commit do estado de falha do Cloud Run Job diário;
- teste de presença dos índices na migration;
- Ruff;
- Mypy;
- Pytest.

