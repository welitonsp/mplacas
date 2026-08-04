# Design de destino — Mplacas

**Data:** 2026-08-04
**Base:** `docs/UI_UX_AUDIT_2026-08-04.md` (HEAD `78d8aaf`)
**Natureza:** proposta de arquitetura e design system. **Nenhuma implementação incluída.**

**Princípio norteador desta proposta:** preservar tudo que a auditoria confirmou como
superior à média (honestidade do dado, tokens semânticos, `Card` base, ausência de
dependência de gráficos, camada técnica fotovoltaica) e corrigir cirurgicamente o que foi
medido como deficiente. **Não há reconstrução do dashboard proposta aqui.**

---

## 1. Arquitetura da informação de destino

### 1.1 Estado atual

Duas rotas: `/login`, `/dashboard`. Sem navegação. Sem shell.

### 1.2 Destino proposto (em três horizontes)

**Horizonte 1 — sem novas páginas.** Corrigir o dashboard existente. Toda a lista P1/P2 de
layout, contraste, redundância e gráfico cabe aqui, sem introduzir rota nenhuma.

**Horizonte 2 — shell de aplicação + duas páginas.** Só quando houver **duas** coisas
distintas a navegar, e não antes (o ADR-067 já registrou explicitamente essa regra ao
recusar criar um shell de configurações para um único campo).

    /dashboard        visão executiva (a página atual, corrigida)
    /alertas          central de alertas — EXIGE endpoint de leitura novo
    /relatorios       relatórios mensais + exportações (backend pronto)

**Horizonte 3 — administração e configuração.**

    /usina            configuração técnica + financeira + localização
    /faturas          faturas pendentes, confirmação, rejeição
    /organizacao      organização, usuários, convites  (exige reviewer)

**Navegação:** barra lateral só quando houver 4+ destinos. Com 2–3, abas no header. Não
criar sidebar para duas rotas.

**Decisão que precisa de confirmação do usuário:** se o produto continua single-tenant de
fato (ADR-045) ou se caminha para multi-usina na UI (ADR-052). O header (P2-14) depende
dessa resposta.

### 1.3 O que fica no dashboard inicial e o que sai

| Bloco | Destino | Justificativa |
|---|---|---|
| Hero (status, saúde, headline, frescor) | **fica, ampliado** | Melhor elemento da interface. Recebe o resumo de atenção (P1-06) e o último dia com dado |
| Qualidade do ciclo | **fica** | Diferencial de honestidade |
| Histórico de produção | **fica, com seletor de período** | P1-07 |
| Real vs. esperada | **fica, rerrotulado** | P1-02 |
| Fluxo de energia | **fica** | Padrão do setor, bem implementado |
| Diagnósticos | **fica**, com resumo espelhado no Hero | P1-06 |
| Tendência | **fica** | |
| Desempenho técnico | **fica, colapsável por padrão** | Público diferente (benchmark 2.7); expandido só sob demanda ou por perfil |
| **"Energia e produção" (4 cards)** | **sai** | Duplica o diagrama de fluxo (P2-01) — **decisão de produto, exige confirmação** |
| Indicadores percentuais (2 cards) | **consolida em 1** | P2-03 |
| Financeiro (8 cards planos) | **reorganiza em 3 blocos** | P2-04 |
| Impacto ambiental | **entra** quando ADR-066 B+ estiver pronto | |
| ROI / payback | **entra** quando ADR-067 C/D/E estiver pronto | |

---

## 2. Wireframe textual da estrutura de destino

Notação: `[n]` = colunas do grid de 12. `md` indicado quando difere de `lg`.

    ┌─ HEADER ─────────────────────────────────────────────────────────────────┐
    │ Mplacas · <Nome da usina>          <Organização> · <usuário> · Sair      │
    └──────────────────────────────────────────────────────────────────────────┘

    FAIXA DE SAÚDE                                          [12] (md: 6)
    ┌──────────────────────────────────────────────────────────────────────────┐
    │ CICLO DE REFERÊNCIA 2026-07                                              │
    │ <headline>                                                               │
    │ Saúde da usina  ▓▓▓▓▓▓▓░░ 82/100      ⚠ 1 crítico · 2 atenção  ↓        │
    │ Dado mais recente: 03/08/2026                          [ Saudável ]      │
    ├──────────────────────────────────────────────────────────────────────────┤
    │ ⚠ Dados parciais neste ciclo: 2 dias ausentes.                           │
    └──────────────────────────────────────────────────────────────────────────┘
      ^ NOVO: chip de atenção com âncora para a seção de diagnósticos (P1-06)

    HISTÓRICO DE PRODUÇÃO            [8] (md: 4)   │ REAL vs. ESPERADA  [4] (md: 2)
    ┌──────────────────────────────────────────────┐ ┌──────────────────────────┐
    │ Histórico diário  ( 7d | 30d | ✓90d )        │ │ PRODUÇÃO NO CICLO        │
    │ 82 de 90 dias com dado coletado              │ │ 412,80 kWh               │
    │ Real vs. média esperada do período: 94,2 %   │ ├──────────────────────────┤
    │                                              │ │ MÉDIA DIÁRIA ESPERADA    │
    │ ▁▃▅▇▅▃▁ ... (barras)                         │ │ 14,90 kWh/dia            │
    │ ─────── média esperada (linha única)         │ │ baseline sazonal         │
    │ 05/05      19/06           03/08  ← na rolagem│ └──────────────────────────┘
    │ [detalhe do dia selecionado, aria-live]      │
    └──────────────────────────────────────────────┘
      ^ P1-02 (rótulo + linha única), P1-05 (régua dentro do scroll),
        P1-07 (seletor), P2-13 (cobertura de dias)

    FLUXO DE ENERGIA                 [7] (md: 3)   │ DIAGNÓSTICOS       [5] (md: 3)
    ┌──────────────────────────────────────────────┐ ┌──────────────────────────┐
    │  Produção ─autoconsumo→ Consumo              │ │ ▌Crítico  <mensagem>     │
    │  412,8 kWh              398,1 kWh            │ │  Ação: <ação>            │
    │  ▓▓▓▓▓▓░░ auto/exportada  ▓▓▓▓░░ auto/import │ │ ▌Atenção  <mensagem>     │
    │            ┌─ Rede ─┐                        │ │  Ação: <ação>            │
    │            │ ← exp  │                        │ └──────────────────────────┘
    │            │ imp →  │                        │ TENDÊNCIA
    └──────────────────────────────────────────────┘ ┌──────────────────────────┐
      ^ absorve os 4 cards removidos (P2-01)         │ 2026-06 → 2026-07 ...    │
                                                     └──────────────────────────┘

    FINANCEIRO                                              [12] (md: 6)
    ┌── Custo do ciclo ──────────┬── Economia ────┬── Créditos de energia ─────┐
    │ R$ 187,45  total           │ R$ 312,90      │ Saldo    248 kWh           │
    │  ├ energia        R$ 142,10│ estimada       │ Cobertura ▓▓▓▓▓░ 78 %      │
    │  └ ilum. pública  R$  45,35│                │                            │
    │ tarifa c/ imp. R$ 0,875126/kWh (apoio)      │                            │
    └────────────────────────────┴────────────────┴────────────────────────────┘
      ^ P2-04 — parte/todo explícito, créditos separados (são energia, não R$)

    [ + Retorno do investimento ]   ← ADR-067 C/D/E
    [ + Impacto ambiental ]         ← ADR-066 B+

    ▸ DESEMPENHO TÉCNICO   (colapsado por padrão)           [12] (md: 6)
      PR bruto | PR corrigido | Yield específico | Disponibilidade de reporte
      Degradação anualizada  |  Por que produzi menos (taxonomia de perdas)

### Justificativa das mudanças de ordem

**A ordem geral é preservada.** As únicas alterações são:

1. **Financeiro sobe** de último para depois de diagnósticos — "quanto custou?" é pergunta
   de proprietário; "PR corrigido por temperatura" é pergunta de técnico. Hoje o
   proprietário precisa atravessar a camada técnica para chegar ao dinheiro.
2. **Técnico desce e colapsa** — mesma justificativa, e alinhado ao benchmark 2.7 e ao
   raciocínio já escrito no comentário da própria `TechnicalPerformanceSection`.
3. **"Energia e produção" desaparece** — absorvida pelo fluxo (P2-01).
4. **Nada mais se move.** Hero, histórico, fluxo e diagnósticos ficam onde estão.

---

## 3. Design system de destino

### 3.1 Tokens de cor

**Regra:** os tokens existentes de *preenchimento* e *marca* **não mudam**. São adicionados
tokens de *texto* de severidade, porque os atuais reprovam em AA quando usados como texto
(P1-03). Isso preserva toda a semântica já testada e corrige apenas a legibilidade.

| Token | Valor atual | Ação | Contraste |
|---|---|---|---|
| `--color-brand-primary` | `#1a56db` | **manter** | 6,18:1 sobre branco |
| `--color-brand-primary-dark` | `#1e429f` | **manter** | 8,99:1 |
| `--color-brand-primary-light` | `#ebf5ff` | **manter** | superfície |
| `--color-surface` | `#ffffff` | **manter** | |
| `--color-surface-subtle` | `#f9fafb` | **manter** | |
| `--color-border` | `#e5e7eb` | **manter** (borda decorativa, isenta de 1.4.11) | |
| `--color-text-primary` | `#111827` | **manter** | 17,74:1 |
| `--color-text-secondary` | `#6b7280` | **manter** | 4,83:1 |
| `--color-success` | `#16a34a` | **manter** (só preenchimento) | |
| **`--color-success-text`** | — | **CRIAR** `#15803d` | **4,54:1** sobre branco |
| `--color-success-light` | `#f0fdf4` | **manter** | |
| `--color-warning` | `#d97706` | **manter** (só preenchimento) | |
| **`--color-warning-text`** | — | **CRIAR** `#b45309` | **4,52:1** sobre branco |
| `--color-warning-light` | `#fffbeb` | **manter** | |
| `--color-danger` | `#dc2626` | **manter** (preenchimento e texto sobre branco) | 4,83:1 |
| **`--color-danger-text`** | — | **CRIAR** `#b91c1c` | **6,29:1** sobre branco, resolve o 4,41:1 sobre `danger-light` |
| `--color-data-secondary` | `#7c3aed` | **manter** | 5,70:1 |
| **`--color-chart-reference`** | hoje `border-gray-400` | **CRIAR** `#6b7280` | 4,83:1 — linha "esperado" |
| **`--color-chart-track`** | hoje `gray-100` | **CRIAR** `#e5e7eb` | melhora a relação barra/trilho para >= 3:1 |
| `GRID_HEX` | `#d1d5db` | **manter** — 4,19:1 contra o azul adjacente, e a legenda tem rótulo textual | |

**Regra de uso (a ser codificada em `visuals.ts`):**

- `SEVERITY_TEXT` passa a apontar para os tokens `-text`.
- `SEVERITY_BG`, `SEVERITY_BAR`, `SEVERITY_DOT`, `SEVERITY_BORDER_L` continuam nos tokens
  atuais.
- **Nenhum componente muda de cor semântica.** Só a variante de texto escurece.

**Regra permanente:** cor nunca é o único portador de significado. Já é respeitado hoje
(`DIAGNOSTIC_SEVERITY_META`, `LEVEL_LABEL`, `EVIDENCE_LEVEL_META` sempre trazem rótulo
textual). Isso deve continuar sendo condição de aceite de qualquer componente novo.

### 3.2 Tipografia

Família: **manter `system-ui`**. Não introduzir webfont. A tentativa anterior (commit não
autorizado `bcd2a42`, Inter via CDN) foi corretamente revertida: acrescenta uma requisição
externa bloqueante, um ponto de falha de terceiro e nenhum ganho mensurável de compreensão.
`system-ui` é a decisão certa e deve ser registrada como decisão, não como omissão.

Escala fechada de seis degraus, a tokenizar em `@theme` (elimina `text-[10px]` e
`text-[11px]` — P2-11):

| Papel | Tamanho | Peso | Uso |
|---|---|---|---|
| `display` | 30px / 1,2 | 600 | valor principal do Hero (se adotado) |
| `value` | 24px / 1,25 | 600 | valor de `MetricCard`, `CurrencyCard` |
| `title` | 16px / 1,4 | 600 | `SectionTitle` (hoje 14px — P2-12) |
| `body` | 14px / 1,5 | 400 | texto corrido, mensagens de indisponibilidade |
| `label` | 12px / 1,4 | 500, uppercase, `tracking-wide` | rótulo de card |
| `caption` | 12px / 1,4 | 400 | legenda, régua de eixo, texto de apoio |

**Piso de 12px.** Nada abaixo disso, incluindo o selo "Parcial" e as réguas do gráfico.

**`tabular-nums` obrigatório** em: valor de card, deltas de tendência, painel de detalhe do
gráfico, valores do fluxo de energia, todos os campos financeiros (P2-09).

**Largura de leitura:** blocos explicativos (`PerformanceRatioCard`,
`ReportingAvailabilityCard`, `YieldCard`) limitados a ~65ch.

### 3.3 Espaçamento e geometria

| Token | Valor | Uso |
|---|---|---|
| espaço interno de card | `p-5` (`sm:p-6` no Hero) | **manter** — já consistente |
| gap do grid de página | `gap-4` / `lg:gap-6` | **manter** |
| gap entre cards de subgrid | `gap-4` | **manter** |
| separação entre seções | vertical do grid | **manter** |
| raio | `rounded-xl` em cards, `rounded-lg` em elementos internos, `rounded-full` em badges/barras | **manter** — já consistente |
| sombra | `shadow-sm` estático | **manter**; `hover:shadow-md` passa a exigir `interactive` (P2-05) |
| borda | 1px `gray-200`; `border-l-4` para acento de severidade | **manter** |

**Regra nova:** nenhum componente define sua própria margem externa (corrige P3-03). O
espaçamento é do container.

### 3.4 Grid e breakpoints

| Breakpoint | Largura | Comportamento de destino |
|---|---|---|
| base | < 640px | 1 coluna, tudo empilhado |
| `sm` | 640px | subgrids em 2 colunas (já ocorre) |
| **`md`** | **768px** | **6 colunas REALMENTE distribuídas** — hoje toda seção é `col-span-6` (P1-04) |
| `lg` | 1024px | 12 colunas, composição bento (já ocorre) |
| `xl` | 1280px | igual a `lg` |
| `2xl` | 1536px | container `96rem`, **spans uniformizados** (hoje só duas seções declaram) |

Container: `max-w-7xl 2xl:max-w-[96rem]` — **manter**, já consistente entre header e main.

### 3.5 Movimento

`transition-colors duration-150` e `transition-shadow duration-150` são o vocabulário
atual — **manter**. Não introduzir animação de entrada, parallax, contadores animados ou
transição de página. Em um produto de auditoria, movimento decorativo custa confiança.

**Adicionar:** respeito a `prefers-reduced-motion` para o `animate-pulse` dos skeletons.

### 3.6 Acessibilidade — condições de aceite permanentes

1. Todo par texto/fundo >= 4,5:1; todo elemento gráfico portador de informação >= 3:1,
   **verificado por teste que calcula a relação**, não por lista de classes proibidas.
2. Cor nunca sozinha: sempre acompanhada de rótulo textual, forma ou posição.
3. Todo controle interativo com `focus-visible` visível (já cumprido).
4. Gráfico navegável por teclado com um único tab stop (já cumprido).
5. Toda `section` com nome acessível (`aria-labelledby` apontando para o `SectionTitle`) —
   **não cumprido hoje**.
6. Hierarquia de headings coerente: um `h1`, `h2` por seção. Hoje o `h2` é um subtítulo
   decorativo menor que os `h3` (P2-12).
7. `prefers-reduced-motion` respeitado.
8. Reflow a 320px e zoom 200% sem perda de conteúdo — rolagem horizontal permitida apenas
   dentro do gráfico, com a régua acompanhando (P1-05).

---

## 4. Catálogo de componentes

Classificação: **manter** · **melhorar** · **consolidar** · **substituir** · **remover** ·
**criar**.

| Componente | Ação | Motivo |
|---|---|---|
| `Card` | **melhorar** | `interactive?: boolean` para o hover (P2-05); `tabular-nums` opcional |
| `MetricCard` | **melhorar** | `tabular-nums`; piso de 12px no selo "Parcial"; token `-text` de aviso |
| `CurrencyCard` | **manter** | Decisão de tratar dinheiro como dado neutro está correta |
| `HeroCard` | **melhorar** | Receber chip de resumo de atenção (P1-06) e último dia com dado; avaliar `role="meter"` (P3-02) |
| `QualityBanner` | **melhorar** | Tokens `-text` (P1-03) |
| `DataFreshness` | **manter** | Um dos melhores componentes do sistema |
| `SectionTitle` | **melhorar** | `text-base`, `text-gray-900`, e emitir `id` para `aria-labelledby` |
| `DiagnosticsCard` | **melhorar** | Remover a margem própria (P3-03); tokens `-text` |
| `TrendCard` / `TrendMetricItem` | **melhorar** | `tabular-nums`; tokens `-text` |
| `EnergyFlowDiagram` | **melhorar** | Absorver o selo "Parcial" dos cards removidos (P2-01); trocar `role="progressbar"` por `role="img"` (P3-01) |
| `ProductionHistoryChart` | **melhorar** | P1-02 (linha única + rótulo), P1-05 (régua no scroll), P1-07 (período), P2-13 (cobertura de dias), `--color-chart-reference` |
| `ProductionHistorySection` | **manter** | Tratamento de estados é exemplar; serve de padrão para os demais |
| `ExpectedProductionCard` | **melhorar** | Rótulo de baseline mais explícito (P1-02) |
| `EstimatedSavingsCard` | **manter** | Padrão-ouro de honestidade do projeto |
| `YieldCard` | **manter** | |
| `PerformanceRatioCard` | **manter** | |
| `SpecificYieldCard` | **manter** | |
| `ReportingAvailabilityCard` | **manter** | Rótulo já evita a confusão com uptime |
| `BaselineDegradationCard` | **manter** | |
| `LossBreakdownSection` | **melhorar** | Tokens `-text` nos badges de evidência |
| `TechnicalPerformanceSection` | **melhorar** | Colapsável por padrão; skeleton dedicado (P2-06) |
| **`EnergyProductionSection`** | **REMOVER** | Duplica o diagrama de fluxo (P2-01) — **decisão de produto** |
| `MetricCardSkeletonGrid` | **consolidar** | Virar `SkeletonGrid` parametrizável por forma, servindo página e seção (P2-06) |
| `DashboardHeader` | **melhorar** | Identidade de usina/organização/usuário (P2-14) |
| `LoginPage` | **melhorar** | `Navigate` declarativo (P3-04); aviso de sessão expirada (P2-07) |
| `ProtectedRoute` | **melhorar** | Propagar motivo do redirecionamento (P2-07) |
| **`AttentionSummary`** | **CRIAR** | Chip "N críticos, N atenção" no Hero, com âncora (P1-06) |
| **`PeriodSelector`** | **CRIAR** | Grupo de botões 7/30/90 dias (P1-07) |
| **`SplitBar`** | **CRIAR** | Barra 100% empilhada com legenda, reutilizada em autossuficiência (P2-03) e no fluxo |
| **`FinancialSummary`** | **CRIAR** | Custo do ciclo com decomposição parte/todo (P2-04) |
| **`ErrorBoundary`** | **CRIAR** | Raiz da aplicação + tela de erro de configuração (P3-05) |
| **`RetryableError`** | **CRIAR** | Extrair o padrão já correto de `ProductionHistorySection` e reusar no erro global (P2-08) |
| **`EnvironmentalImpactCard`** | **CRIAR** | Quando ADR-066 B+ existir. Fator, fonte e versão sempre visíveis |
| **`FinancialReturnSection`** | **CRIAR** | Quando ADR-067 C/D/E existir. Cobertura `cycles_counted`/`cycles_expected` obrigatória, payback sempre rotulado como projeção |

**Nenhum componente duplicado é proposto. Nenhum código morto foi encontrado no HEAD.**

---

## 5. Decisões que exigem confirmação explícita do usuário

Estas **não** devem ser executadas pelo worker sem resposta do usuário:

1. **Mover o cálculo de produção esperada para o backend** (P1-01) — muda contrato de dois
   endpoints em produção. Provavelmente merece um ADR próprio (ADR-068).
2. **Remover a seção "Energia e produção"** (P2-01) — retira informação hoje visível.
3. **Colapsar a seção de desempenho técnico por padrão** — muda o que o usuário vê ao abrir.
4. **Rerrotular "Esperado" para "Média diária esperada (baseline sazonal)"** (P1-02) — muda
   o significado percebido de um número já publicado.
5. **Rumo do header:** single-tenant (ADR-045) ou multi-usina na UI (ADR-052)? Determina
   P2-14 e o Horizonte 3 inteiro.
6. **Ordem: financeiro antes de técnico** — reordenação visível da página.

---

## 6. O que esta proposta deliberadamente NÃO faz

- **Não redesenha o dashboard.** A estrutura em blocos e o grid bento são preservados.
- **Não introduz webfont.** `system-ui` é decisão consciente.
- **Não introduz biblioteca de gráficos.** 86 kB gzip é vantagem competitiva.
- **Não introduz dark mode.** Sem demanda evidenciada; custo de manutenção de tokens alto.
- **Não introduz glassmorphism, gradientes decorativos ou sombras pesadas.**
- **Não toca em nenhuma fórmula, arredondamento ou unidade.**
- **Não cria página para preencher menu.** Cada rota proposta tem endpoint e pergunta de
  usuário associados.
