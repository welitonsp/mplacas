# ADR-072 — Módulos do painel em rotas separadas

## Status

Aceito (2026-08-08).

## Contexto

O dashboard (`frontend/src/pages/DashboardPage.tsx`) recebeu nota 4/10 do usuário: "parece uma
tela com lista de cards". Um diagnóstico grounded (`product-uiux-lead`, comparando com 5
concorrentes reais de monitoramento solar — SolarEdge, Enphase, Enlighten, Fronius Solar.web, SMA
Sunny Portal, Tesla App) confirmou causas raiz reais no código: 10 seções empilhadas verticalmente
numa única rota, hierarquia tipográfica achatada (`h2`/`h3` com a mesma classe), o elemento que
deveria ser o hero visual (`EnergyFlowDiagram`) enterrado como a 5ª de 10 seções, ~1,5 tela abaixo
da dobra.

O plano original de correção reorganizava a hierarquia visual dentro da mesma página. Ao revisar,
o usuário pediu explicitamente para dividir em **módulos separados por tipo de análise**, decidindo:
**rotas separadas por módulo** (URL própria, não abas na mesma URL) e o agrupamento **Visão Geral /
Produção / Financeiro / Técnico**.

Este ADR registra a arquitetura de rotas/módulos decidida (`frontend-architect`), como pré-requisito
estrutural para o redesenho visual já aprovado (faixa hero de marca na Visão Geral, gráfico de
ciclos em colunas verticais na Produção, tira de dados compacta no Financeiro, animação sutil de
entrada) — que passa a ser implementado por módulo, depois que a estrutura existir.

### Achado crítico levantado durante o planejamento

Os testes de frontend **não rodam no CI**. `.github/workflows/ci.yml` (job `frontend`) executa
`npm audit`, `npm run type-check` e `npm run build` — nenhum `npm test`/`vitest`. "CI verde" hoje
prova que compila, não que funciona. Uma migração incremental que se apoia em "CI verde" por etapa
exige corrigir isso primeiro (Etapa 0 abaixo), senão a rede de segurança é ilusória.

## Decisão

### 1. Estrutura de rotas — layout aninhado, não 4 rotas irmãs

```
/dashboard                  → redirect (replace) para /dashboard/visao-geral, preservando ?plant=
/dashboard/visao-geral
/dashboard/producao
/dashboard/financeiro
/dashboard/tecnico
/dashboard/*                → mesmo redirect (sub-rota desconhecida)
```

`/dashboard` sobrevive só como redirect (não como conteúdo próprio) — os 4 módulos são simétricos,
nenhum é "especial", e `LoginPage.tsx`/o catch-all de `App.tsx` continuam apontando para `/dashboard`
sem quebrar bookmarks antigos.

Rota de layout com `<Outlet/>` (`react-router` v8, já instalado — nenhuma dependência nova):

```tsx
<Route path="/dashboard" element={<ProtectedRoute><PlantProvider><DashboardLayout/></PlantProvider></ProtectedRoute>}>
  <Route index element={<DashboardIndexRedirect/>} />
  <Route path="visao-geral" element={<OverviewPage/>} />
  <Route path="producao" element={<ProductionPage/>} />
  <Route path="financeiro" element={<FinancialPage/>} />
  <Route path="tecnico" element={<TechnicalPage/>} />
  <Route path="*" element={<DashboardIndexRedirect/>} />
</Route>
```

**Por que aninhada e não 4 rotas irmãs**: com rota de layout, `PlantProvider` monta uma vez e não
remonta ao navegar entre módulos — nenhum refetch de `GET /plants`, nenhuma re-resolução de usina.
Com 4 rotas irmãs, cada uma envolvendo seu próprio `PlantProvider`, cada clique no sub-nav dispararia
`/plants` de novo. Verificado por teste (`fetchPlants` chamado exatamente 1× após navegar pelos 4).

**Armadilha evitada**: `<Navigate to="/dashboard/visao-geral" replace/>` descartaria a query string.
`PlantContext` lê `?plant=` uma vez, na montagem — um redirect ingênuo quebraria link compartilhado
de usina específica, silenciosamente. `DashboardIndexRedirect` preserva `location.search`.

### 2. Distribuição das seções

| Módulo | Conteúdo | Recursos buscados |
|---|---|---|
| **Visão Geral** | `HeroCard`+`QualityBanner` (faixa hero) + `EnergyFlowDiagram` + `StackedBar` de autossuficiência + `DiagnosticsCard` + `TrendCard` | `executive`, `anomalies` (só para `latestDataDate`) |
| **Produção** | `MonthlyProductionSection` (12 ciclos) + `ProductionHistorySection` (90 dias) + `LatestDailyProductionCard` | `anomalies`, `pvSummary` (esperado), `monthlyHistory` |
| **Financeiro** | `FinancialSection` inteira (custo do ciclo + tarifas/créditos + retorno do investimento) | `executive`, `financialReturn` |
| **Técnico** | `TechnicalPerformanceSection` (PR, yield, disponibilidade, degradação, perdas) — **sem o toggle expandir/colapsar** | `pvSummary` |

Nenhuma seção mudou de módulo em relação à proposta original do usuário — confirmado lendo o
conteúdo real de cada bloco (`ExecutiveTrend` não carrega métrica financeira, então `TrendCard`
pertence a Visão Geral, não Financeiro).

**Toggle do Técnico removido**: a divulgação progressiva existia para não poluir uma página longa;
numa rota que o usuário escolhe deliberadamente, a navegação já é a divulgação progressiva. Chave
`mplacas:technical-performance-expanded` vira estado morto, removida.

**Amarração preservada**: o chip "N críticos" do `HeroCard` linka para `#diagnosticos` — os dois
ficam no mesmo módulo (Visão Geral), verificado explicitamente na etapa correspondente.

### 3. Fronteira de fetch: por módulo, sem pré-busca e sem cache

Cada módulo busca só os recursos que usa, via `usePlantResource` (já independente por recurso desde
a refatoração do `DashboardPage`, ver commits desta mesma sessão). `DashboardLayout` não chama
nenhum `usePlantResource` — não deve virar um novo ponto de acoplamento com outro nome.

**Efeito**: Visão Geral (a rota de aterrissagem, 100% das sessões) cai de 5 requisições em voo para
2. Custo aceito: reentrar num módulo já visitado mostra esqueleto de novo, porque `usePlantResource`
não tem cache — o estado vive na instância do hook, desmontou, morreu.

**Alternativa rejeitada**: pré-buscar tudo no `DashboardLayout` recriaria o acoplamento do
`DashboardPage` atual com outro nome de arquivo, e pagaria as 3 requisições extras para quem só quer
ver a Visão Geral — exatamente o custo que a modularização deveria eliminar.

**Reversibilidade barata, decidida agora**: se o flash de esqueleto ao reentrar incomodar no uso
real, a correção é stale-while-revalidate **dentro do próprio `usePlantResource`** (cache por
`(recurso, plantId)`, com limpeza no `logout`) — mudança interna ao hook, invisível para os 4
módulos. Por ser reversível de graça, o ramo simples é escolhido agora.

### 4. O que fica compartilhado (fora de qualquer módulo)

`AppHeader` (logo, `PlantSelector`, ícone de tema, menu do usuário), `DashboardNav` (sub-nav com os
4 links, `NavLink` com `aria-current="page"` nativo), `PlantProvider`, `ProtectedRoute` — sem
mudança de comportamento. Troca de usina preserva a rota atual por construção
(`PlantContext.selectPlant` já usa `setSearchParams(..., {replace:true})`, que só toca a query
string, nunca o pathname).

### 5. Migração: estrutura antes do visual

Ordem decidida: **modularizar primeiro, redesenhar depois**, módulo por módulo. Razão decisiva: a
animação de entrada aprovada ("uma vez, nunca em refetch") ganha um significado diferente com
rotas — toda entrada num módulo é uma montagem nova, então "uma vez" precisa ser redefinido como
"uma vez por entrada no módulo", decisão que só faz sentido depois que o roteamento existir.

**Etapa 0** — adicionar `npm test` ao job `frontend` do CI (pré-requisito, não negociável).
**Etapa 1** — casca de rotas (layout aninhado, 4 paths, `DashboardNav`, `AppShell` com slot
`subnav`); as 4 rotas renderizam o `DashboardPage` atual temporariamente, sem mover conteúdo.
**Etapa 2** — módulo Técnico (o menor, 1 recurso) + extração do harness de teste compartilhado
(`dashboardFixtures.ts`, `renderModule.tsx`).
**Etapa 3** — módulo Financeiro.
**Etapa 4** — módulo Produção.
**Etapa 5** — módulo Visão Geral + remoção do `DashboardPage.tsx`.
**Etapa 6** — consolidação de chrome (`RefreshBar` extraído, `h1`/`document.title`/foco por rota,
remoção do toggle do Técnico).
**Etapas 7+** — redesenho visual aprovado, um módulo por etapa (faixa hero → colunas verticais →
tira financeira → animação de entrada, por último).
**Etapa 8 (opcional, depois)** — `React.lazy` por módulo, com medição de delta de bundle.

## Consequências

### Positivas

- Rota de aterrissagem sai de 5 para 2 requisições em voo.
- Cada mudança visual futura toca um módulo pequeno, não uma página de 600+ linhas — revisão e CI
  por etapa ficam mais baratos.
- Deep link por módulo funciona sem mudança de infra (`frontend/public/_redirects` já serve
  `/* /index.html 200`).
- Nenhuma dependência nova (`react-router` v8 já instalado).

### Negativas

- Reentrar num módulo já visitado mostra esqueleto (sem cache nesta fase) — mitigação futura
  documentada na Decisão 3, sem custo de migração se adotada depois.
- `ProtectedRoute` não guarda a URL tentada antes de expirar sessão — expirar em `/dashboard/financeiro`
  e voltar sempre em `/dashboard/visao-geral` é um incômodo novo com 4 módulos que não existia com
  rota única. Registrado como follow-up, não bloqueia esta migração.
- `DashboardPage.test.tsx` (16 testes) precisa de remapeamento explícito para os módulos —
  particularmente os testes que afirmam ausência "na página inteira" (ex.: frase de streak aparece
  exatamente uma vez), que precisam de um teste novo cruzando os 4 módulos
  (`modules.redundancy.test.tsx`) para continuar significando algo.

## Validação

- `fetchPlants` chamado exatamente 1× ao navegar pelos 4 módulos (prova que `PlantProvider` não
  remonta).
- `/dashboard?plant=X` → `/dashboard/visao-geral?plant=X` (prova que o redirect preserva a usina
  selecionada).
- Troca de usina em qualquer módulo preserva o pathname atual.
- Cada módulo dispara só as requisições da sua tabela de recursos (ausência verificada, não só
  presença).
- Usuário deslogado é barrado nas 4 URLs.
- `npm test` executando no CI a partir da Etapa 0.

## Reversibilidade

Alta para a fronteira de fetch (decisão isolada dentro de `usePlantResource`, ver Decisão 3). Média
para a estrutura de rotas: reverter para uma página única exigiria remontar o `DashboardPage` a
partir dos 4 módulos — mecânico, mas não trivial, dado que os testes já teriam migrado.

## Riscos e o que fica fora de escopo

- Code splitting por módulo (`React.lazy`) fica para depois da migração estrutural, como etapa
  opcional separada — não fazer junto, muda a semântica de carregamento.
- Gerência de foco/`document.title` por rota entra na Etapa 6, não antes.
- A definição operacional de "animação uma vez" (por módulo vs. por sessão) fica para a etapa visual
  correspondente, depois que o roteamento existir.
