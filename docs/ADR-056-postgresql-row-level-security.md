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

- inventário completo das tabelas diretas, filhas e netas, incluindo outbox e séries temporais —
  **concluído em 2026-08-02** e protegido por comparação automática com as 24 tabelas do
  `Base.metadata`; detalhes em `RLS_ROLLOUT_INVENTORY.md`;
- todas as factories HTTP/jobs vinculam tenant ou plataforma antes da primeira query —
  **concluído em 2026-08-02** para todos os consumidores diretos de `SessionFactory()`, com teste
  arquitetural que falha se uma nova sessão não contextualizar como primeira operação;
- roles runtime/migration separadas no Neon e verificadas por teste — **concluído em produção em
  2026-08-02**: `mplacas_runtime` está sem ownership e `BYPASSRLS`, enquanto `neondb_owner` ficou
  restrito ao endpoint direto de migrations;
- migrations com policies `USING` e `WITH CHECK`, `ENABLE` e `FORCE RLS` — **concluído em
  2026-08-02** nas revisões 0039/0040, com trava de aprovação explícita;
- testes PostgreSQL de leitura, inserção, atualização e exclusão cross-tenant — **concluído em
  2026-08-02** para ownership direto, planta, dispositivo, energia diária, auditoria e plataforma;
- canário isolado e rollback ensaiado — **concluído em banco Neon descartável em 2026-08-02**;
  produção permaneceu com zero tabelas RLS. A criação pelo painel de uma branch Neon separada não
  foi possível sem sessão autenticada, por isso o ensaio usou database isolado no endpoint direto.

Até os gates restantes serem atendidos, filtros de aplicação continuam sendo o controle produtivo
e o item permanece parcial no checklist. Não habilitar policies nas tabelas reais antes do canário
em branch descartável, da modelagem tenant de auditoria e da autorização mínima de plataforma.

## Evidência da fundação de rollout — 2026-08-02

- `mplacas.db.rls_inventory` mantém a classificação executável das tabelas.
- Contexto transacional foi aplicado às rotas HTTP, autenticação, readiness, jobs, retenção,
  coletores, drains de relatórios/outbox e webhook Telegram.
- Descobertas globais usam contexto de plataforma explícito; após resolver a organização, o
  Telegram troca para contexto tenant antes das consultas e escritas da fatura.
- Validação local: **626 passed**, **4 skipped**, Ruff e Mypy aprovados.
- Nenhuma migration `ENABLE/FORCE ROW LEVEL SECURITY` foi criada ou aplicada nesta etapa.
- O PR #93 foi integrado e implantado na revisão `mplacas-api-00017-vst`; `/health`, `/ready`,
  smoke e watchdog foram aprovados. A inspeção posterior confirmou zero tabelas com RLS
  habilitado/forçado e a role runtime ainda sem `BYPASSRLS`.

## Evidência do canário de policies — 2026-08-02

- `audit_events` ganhou `organization_id` nullable e `alert_delivery_records` ganhou `plant_id`
  nullable com deduplicação por planta, preservando registros históricos de plataforma.
- O contexto gravado em `session.info` é reaplicado automaticamente após cada novo `BEGIN`,
  cobrindo serviços que fazem `commit()` e reutilizam a mesma sessão.
- A migration 0040 cobre exatamente as 24 tabelas do inventário e exige a aprovação literal
  `MPLACAS_RLS_ACTIVATION_APPROVED=ENABLE-RLS-20260802`.
- O canário final `mplacas_rls_canary_20260803_a051b1a5` confirmou 24 tabelas com
  `ENABLE/FORCE`, 24
  policies e duas funções auxiliares; os testes PostgreSQL cross-tenant passaram.
- O downgrade para 0039 confirmou zero tabela protegida, zero policy e zero função; o re-upgrade
  restaurou 24/24/2 e os testes passaram novamente.
- O database e todas as roles efêmeras foram removidos. Produção continuou com zero RLS ativo.
- O ciclo opcional de toda a história até `base` encontrou oscilação de conexão durante migrations
  antigas; ele permanece disponível por `--full-history-cycle`, mas não integra o gate da 0040.

## UUIDs legados e rollback preventivo — 2026-08-03

A primeira ativação produtiva demonstrou uma premissa ausente no canário original: organizações
legadas usam UUIDs canônicos sentinela com nibble de versão `0`. O helper da 0040 aceitava apenas
versões 1–5 e, corretamente em modo fail-closed, devolvia `NULL`; isso também ocultava o tenant
legítimo. A ativação foi revertida para 0039 antes do aceite.

A 0041 mantém os 36 caracteres canônicos e posições de hífen, mas não restringe a versão/variante.
O teste PostgreSQL usa `00000000-0000-0000-0000-000000000001/2`, impedindo que um futuro canário
volte a validar apenas UUIDv4 novos. O rollback operacional continua sendo 0041/0040 → 0039.
