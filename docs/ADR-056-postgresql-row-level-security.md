# ADR-056 — PostgreSQL Row-Level Security fail-closed

**Data:** 2026-08-01
**Status:** Aceito para prova de conceito; rollout produtivo condicionado aos gates abaixo

## Contexto

O isolamento atual é aplicado na API e nos repositórios. Essa defesa é necessária, mas uma query
nova sem filtro de organização ainda pode atravessar tenants. O P2-01 exige uma segunda barreira no
PostgreSQL sem transformar RLS em um controle apenas nominal.

Ativar `FORCE ROW LEVEL SECURITY` imediatamente nas tabelas reais não é seguro: autenticação,
webhooks e jobs ainda possuem transações de descoberta/plataforma que não vinculam tenant antes da
primeira query. O usuário runtime também pode coincidir com o owner das tabelas no Neon.

## Decisão

Adotar o seguinte contrato:

1. O tenant é definido por transação com
   `set_config('mplacas.organization_id', '<uuid>', true)`. O terceiro argumento `true` equivale a
   `SET LOCAL`, impedindo vazamento de contexto pelo pool.
2. Sem contexto, policies retornam zero linhas e rejeitam escrita (`WITH CHECK`).
3. Bypass requer simultaneamente `mplacas.platform_bypass = 'on'` e membership em uma role
   PostgreSQL dedicada, sem `BYPASSRLS`. Apenas mudar a variável não concede acesso.
4. Tabelas pertencentes diretamente à organização usam `organization_id`; tabelas filhas resolvem
   ownership pela cadeia `plant -> organization`. Tabelas netas usam joins equivalentes.
5. Produção deve usar role runtime sem ownership, sem superuser e sem `BYPASSRLS`; migrations usam
   identidade separada. As tabelas recebem `ENABLE` e `FORCE ROW LEVEL SECURITY`.
6. Operações de plataforma devem chamar `set_platform_context()` explicitamente e ser auditadas.

## Prova de conceito versionada

`tests/test_postgres_rls.py` cria roles e tabela isoladas no PostgreSQL do CI e demonstra:

- query sem tenant retorna zero;
- tenant A não lê nem grava como tenant B;
- contexto `LOCAL` desaparece ao terminar a transação;
- solicitar bypass com role comum continua retornando zero;
- role de plataforma autorizada obtém acesso somente após bypass explícito.

O helper comum está em `db/tenant_context.py`. A prova não habilita policies nas tabelas reais,
evitando rollout parcial inseguro.

## Gates para rollout produtivo

- inventário completo das tabelas diretas, filhas e netas, incluindo outbox e séries temporais;
- todas as factories HTTP/jobs vinculam tenant ou plataforma antes da primeira query;
- roles runtime/migration separadas no Neon e verificadas por teste;
- migrations com policies `USING` e `WITH CHECK`, `ENABLE` e `FORCE RLS`;
- testes PostgreSQL de leitura, inserção, atualização e exclusão cross-tenant;
- canário em branch Neon descartável, métricas de violações e rollback ensaiado.

Até esses gates serem atendidos, filtros de aplicação continuam sendo o controle produtivo e o item
permanece parcial no checklist.
