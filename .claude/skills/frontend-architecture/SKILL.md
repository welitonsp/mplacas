---
name: frontend-architecture
description: Use ao planejar reorganização de rotas, módulos ou fronteiras de responsabilidade no frontend Mplacas. Evita overengineering para um app pequeno (2 rotas reais hoje); toda proposta de estrutura nova precisa de motivo concreto, não hipotético.
---

# Frontend Architecture — Mplacas

## Finalidade
Guiar decisões de estrutura de pastas, rotas e fronteiras de módulo no frontend, calibradas ao tamanho real do produto — não ao tamanho que um SaaS B2B genérico "deveria" ter.

## Quando usar
- Antes de propor uma reestruturação de pastas/rotas.
- Quando `DashboardPage.tsx` ou outro arquivo central voltar a crescer além do sustentável.
- Ao decidir onde um componente/lib novo deve morar.

## Quando não usar
- Para decisão de UX/hierarquia visual (isso é `premium-product-ux`/`information-architecture`).
- Para escolha de biblioteca de gráfico (proibido sem ADR — ver `chart-standards`).

## Entradas necessárias
- Estado real do repositório (rode `repository-ground-truth` primeiro).

## Procedimento
1. Confirme o número real de rotas/módulos existentes hoje (`Grep` em `App.tsx`) antes de propor qualquer estrutura `modules/*` — não assuma que o produto já é grande.
2. Para cada proposta de nova pasta/módulo, responda: existe uma segunda instância real desse padrão hoje, ou é especulação de crescimento futuro? Se for só especulação, não crie a estrutura ainda.
3. Prefira composição simples (`PlantContext`, `AuthContext` como estão) a introduzir uma lib de state management nova sem dor real que a justifique.
4. Ao propor separar um arquivo grande, identifique as fronteiras por responsabilidade real (dado vs. apresentação vs. contexto), não por tamanho de arquivo isolado.
5. Toda proposta é um plano em etapas verificáveis para o worker, nunca o código pronto.

## Critérios de saída
- Proposta cita o(s) arquivo(s) reais afetados, não uma estrutura hipotética.
- Nenhuma dependência nova sem ADR.
- Migração incremental, reversível por etapa.

## Anti-patterns
- Criar `src/modules/` de 20 pastas para um app de 2 páginas reais.
- Introduzir Redux/Zustand/Recoil sem dor concreta de prop-drilling documentada.
- Reescrever em vez de migrar incrementalmente.

## Checklist
- [ ] Motivo concreto (não hipotético) documentado
- [ ] Arquivos afetados listados
- [ ] Plano em etapas reversíveis
- [ ] Nenhuma dependência nova sem ADR
