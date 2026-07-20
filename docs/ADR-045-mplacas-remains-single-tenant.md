# ADR-045 - Mplacas permanece single-tenant (Fase 3 da RBAC descartada)

## Status

Aceito.

## Contexto

O ADR-043 previa, como Fase 3 opcional da evolução RBAC, a introdução de tenants e claims, com o
escopo de usina derivado do tenant do usuário. Antes de implementar, foi necessário confirmar o
rumo de produto: o Mplacas atenderá múltiplas organizações isoladas na mesma instância, ou apenas
a operação própria de reconciliação entre a telemetria NEPViewer e as faturas da Equatorial?

A decisão de produto é: **single-tenant**. O sistema serve uma única operação.

## Decisão

A Fase 3 (tenants e claims) é **descartada**, não adiada. Introduzir uma entidade de tenant,
com o isolamento de dados, os joins adicionais e a camada de autorização que ela exige, adicionaria
complexidade estrutural permanente sem entregar valor em um contexto single-tenant. Isso contraria o
princípio orientador "integridade antes de automação": cada camada precisa se pagar em garantia
real, não em generalidade especulativa.

O modelo de autorização atual é considerado **completo** para o escopo do produto:

- papéis `ADMIN` e `READ` (ADR-043);
- escopo por usina definido diretamente na credencial (ADR-043);
- usuários nomeados como donos de credenciais, com expiração e desativação em cascata (ADR-044).

## Consequências

### Positivas

- O modelo de dados permanece direto: credenciais e usuários, sem uma camada de tenant.
- O esforço de engenharia é redirecionado para melhorias P1 de valor operacional imediato
  (fila/workers e particionamento/retenção).

### Negativas

- Uma futura decisão de tornar o produto multi-tenant exigiria retomar este trabalho. O risco é
  aceito: a migração para multi-tenant, se ocorrer, será orientada por requisitos reais e não por
  antecipação.

## Reversibilidade

Caso o produto evolua para multi-tenant, o ponto de extensão natural é associar `operational_users`
a um `tenant_id` e derivar o escopo de usina a partir do tenant, preservando os papéis e a mecânica
de credenciais já existentes. Este ADR deve ser revisto e substituído nesse cenário.
