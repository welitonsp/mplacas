# ADR-035 - Escopo obrigatorio de faturas por usina

## Status

Aceito.

## Contexto

A auditoria tecnica profunda identificou que `utility_bills.plant_id` ainda era nullable para
compatibilidade com faturas legadas. Essa excecao obrigava os servicos de inteligencia a aceitarem
faturas sem usina quando havia apenas uma planta cadastrada, criando uma regra especial que nao
escala para multiusina, tenants ou RBAC por escopo.

## Decisao

1. Tornar `utility_bills.plant_id` obrigatorio no modelo SQLAlchemy.
2. Adicionar migration que:
   - preenche faturas legadas sem `plant_id` quando existe exatamente uma planta;
   - falha com mensagem operacional clara quando existem faturas legadas e nao ha uma unica planta
     inequivoca;
   - altera a coluna para `NOT NULL`.
3. Exigir `plant_id` resolvido em `UtilityBillRepository.create_pending`, `get` e `list_pending`.
4. Remover os atalhos de escopo legado dos servicos de ciclo, historico e dashboard executivo.
5. Manter a conveniencia de inferir `plant_id` na API de billing quando existe exatamente uma planta.
6. Permitir intake de fatura pelo Telegram somente quando existe exatamente uma planta configurada.

## Consequencias

### Positivas

- Toda fatura fica inequivocamente vinculada a uma usina.
- Consultas de inteligencia deixam de misturar faturas legadas em ambientes multiusina.
- A base fica mais preparada para tenants, claims e autorizacao por `plant_id`.
- A migration protege producao contra backfill ambiguo.

### Negativas

- Ambientes com faturas legadas e zero ou multiplas plantas precisam corrigir dados antes da
  migration.
- O Telegram nao consegue receber faturas em instalacoes multiusina ate existir selecao explicita de
  usina no fluxo conversacional.

## Validacao

A entrega deve permanecer coberta por:

- teste de contrato da migration;
- testes de repository e billing router;
- testes de ciclo, historico e dashboard executivo;
- teste do escopo de intake via Telegram;
- Ruff;
- Mypy;
- Pytest.
