# Roteiro de implementação de UI/UX — Mplacas

**Data:** 2026-08-04
**Base:** `docs/UI_UX_AUDIT_2026-08-04.md` e `docs/UI_UX_TARGET_DESIGN_2026-08-04.md`
**Estado:** proposta. **Nada foi implementado.** Nenhuma etapa deve começar antes da
aprovação do diagnóstico pelo usuário.

---

## 0. Regras que valem para todas as etapas

1. **Nenhuma etapa altera fórmula, arredondamento ou unidade.** Critério de aceite
   universal: os testes financeiros e de contrato existentes passam **sem edição**.
2. **Nenhuma etapa converte ausência em zero** nem esconde dado incompleto.
3. Cada etapa termina com `npm run type-check`, `npm run test` e `npm run build` verdes.
4. Cada etapa acrescenta pelo menos um teste que **falharia antes** dela.
5. Etapas que tocam `billing`, `auth`, `credentials`, `organizations`, `audit` ou
   `migrations` passam pelo **reviewer** antes de serem dadas por concluídas (`CLAUDE.md`).
6. **Nenhum commit, push ou PR sem autorização expressa do usuário.**
7. Etapas marcadas **[BLOQUEADA]** dependem de decisão do usuário registrada na seção 5 do
   documento de design de destino.

---

## 1. Onda 1 — correções de baixo risco, alto retorno (sem decisão pendente)

Todas cabem no dashboard existente. Nenhuma toca contrato, cálculo ou rota.

### Etapa 1.1 — Contraste AA medido (P1-03)
- Criar `--color-success-text`, `--color-warning-text`, `--color-danger-text`,
  `--color-chart-reference`, `--color-chart-track` em `index.css`.
- Apontar `SEVERITY_TEXT` para os tokens `-text`; manter `SEVERITY_BG/BAR/DOT/BORDER_L`.
- Trocar `border-gray-400` da linha de referência por `--color-chart-reference`.
- Trocar o trilho das barras de progresso para `--color-chart-track`.
- **Substituir `colorContrast.test.tsx`** por um teste que **calcula** a relação de
  contraste de cada par declarado e falha abaixo de 4,5:1 (texto) e 3:1 (gráfico).
- **Aceite:** os 8 pares reprovados da auditoria passam; nenhum componente muda de cor
  semântica. **Esforço:** S. **Risco:** baixo. **Reviewer:** não.

### Etapa 1.2 — Grid real em `md` e `2xl` uniforme (P1-04)
- Distribuir spans em `md` (nenhuma seção continua `md:col-span-6` por padrão).
- Uniformizar as declarações `2xl` entre as seções.
- Ajustar `MetricCardSkeletonGrid` para espelhar a nova malha.
- **Aceite:** teste que afirma que em `md` pelo menos duas seções distintas declaram span
  menor que a linha inteira. **Esforço:** S. **Risco:** baixo. **Reviewer:** não.

### Etapa 1.3 — Régua de datas dentro do container rolável (P1-05)
- Mover a linha de datas para dentro do `overflow-x-auto`, com a mesma `minWidth`.
- **Aceite:** teste de DOM afirmando que o elemento das datas é descendente do container
  com `minWidth`. **Esforço:** S. **Risco:** baixo. **Reviewer:** não.

### Etapa 1.4 — Desredundância sem remoção de informação (P2-02, P2-03)
- Remover a frase duplicada de streak em `DashboardPage` (fica só no gráfico).
- Consolidar "Autossuficiência" e "Dependência da rede" em um card com barra 100%
  empilhada (`SplitBar` novo), com os dois percentuais rotulados.
- **Aceite:** teste afirmando que o texto de streak aparece exatamente uma vez; teste
  afirmando que os dois percentuais continuam legíveis como texto. **Esforço:** S.

### Etapa 1.5 — Tipografia, números tabulares e hierarquia de seção (P2-09, P2-11, P2-12)
- Tokenizar a escala de seis degraus em `@theme`; eliminar `text-[10px]`/`text-[11px]`;
  piso de 12px.
- `tabular-nums` nos valores.
- `SectionTitle` para `text-base font-semibold text-gray-900`, emitindo `id`.
- Resolver o `h2` "Dashboard executivo" (remover ou promover).
- **Aceite:** teste que falha se qualquer componente contiver `text-[` com valor menor que
  12px. **Esforço:** M. **Risco:** baixo, mas de alcance visual amplo — pede revisão
  visual humana antes de fechar.

### Etapa 1.6 — Estados e casca (P2-05, P2-06, P2-08, P2-10, P3-03, P3-04, P3-05)
- `Card` com `interactive?: boolean`; hover só quando `true`.
- `SkeletonGrid` parametrizável; skeleton dedicado da seção técnica.
- Extrair `RetryableError` do padrão de `ProductionHistorySection` e usar no erro global.
- Favicon próprio, `meta description`, `theme-color`, `manifest.webmanifest`,
  `apple-touch-icon`.
- `ErrorBoundary` na raiz e tela de erro de configuração legível quando `env.ts` lança.
- `DiagnosticsCard` sem margem própria; `LoginPage` com `Navigate` declarativo.
- **Aceite:** `dist/` contém o favicon referenciado por `index.html`. **Esforço:** M.

### Etapa 1.7 — Resumo de atenção no Hero (P1-06)
- `AttentionSummary`: chip "N críticos, N atenção" derivado de `combineDiagnostics`, com
  âncora para a seção de diagnósticos. Zero diagnósticos significa nada renderizado.
- **Aceite:** teste com 1 crítico e 2 atenção afirmando a contagem e o alvo da âncora.
- **Esforço:** S. **Risco:** baixo.

---

## 2. Onda 2 — interação e integridade do gráfico

### Etapa 2.1 — Seletor de período (P1-07)
- `PeriodSelector` (7/30/90 dias) governando o parâmetro `days`.
- Rótulo do gráfico e percentual agregado refletem o período selecionado.
- **Aceite:** teste afirmando que trocar o período dispara nova busca com o `days` correto
  e que o rótulo acompanha. **Esforço:** S–M.

### Etapa 2.2 — Cobertura de dias e lacunas visíveis (P2-13)
- Exibir "N de M dias com dado coletado" usando `start_date`/`end_date` do payload.
- Representar dias sem dado como lacuna no eixo, não como ausência de barra.
- Tratar `null` explicitamente como lacuna, eliminando o `?? 0` latente.
- **Aceite:** teste com 3 dias faltando no meio da janela afirmando que o texto de
  cobertura aparece e que nenhuma barra de zero é criada. **Esforço:** M.

### Etapa 2.3 — [BLOQUEADA] Rótulo honesto da expectativa (P1-02)
- Depende da decisão 4 da seção 5 do design de destino.
- Linha única de referência horizontal; rótulo "Média diária esperada (baseline sazonal)";
  agregado como "Real vs. média esperada do período", com premissa visível.
- **Esforço:** S. **Risco:** baixo tecnicamente, **alto em percepção** — muda o significado
  de um número já publicado em produção.

---

## 3. Onda 3 — contrato e arquitetura (exige ADR e confirmação)

### Etapa 3.1 — [BLOQUEADA] Expectativa de produção no backend (P1-01)
- **Pré-requisito: ADR novo (sugestão ADR-068)** decidindo mover o cálculo para o backend,
  com versão de modelo no padrão `MPLACAS_<DOMINIO>_V<N>`.
- Sequência obrigatória, sem quebra em produção:
  1. Backend passa a devolver `expected_daily_production_kwh` e a versão em
     `/photovoltaic/summary`. Nada muda no cliente. **Reviewer: sim.**
  2. Frontend passa a ler o campo; `deriveExpectedDailyProduction` deixa de existir.
  3. `/energy/anomalies/latest` resolve a expectativa internamente; o parâmetro de query é
     depreciado com prazo. **Reviewer: sim.**
- **Aceite:** nenhuma chamada do frontend envia expectativa de produção ao servidor;
  `photovoltaic-contracts.ts` não contém multiplicação de grandezas energéticas.

### Etapa 3.2 — [BLOQUEADA] Reorganização do financeiro (P2-04)
- Três blocos: Custo do ciclo (com decomposição parte/todo), Economia, Créditos.
- Tarifas como linha de apoio.
- **Aceite explícito:** todo teste financeiro existente passa **sem edição**; nenhum valor,
  unidade ou número de casas decimais muda. **Reviewer: sim** (toca apresentação de
  billing).

### Etapa 3.3 — [BLOQUEADA] Remoção de "Energia e produção" (P2-01)
- Absorver o selo "Parcial" no diagrama de fluxo **antes** de remover a seção.
- **Aceite:** teste afirmando que importada, injetada, autoconsumo e consumo aparecem
  exatamente uma vez na página. **Reviewer:** não.

### Etapa 3.4 — [BLOQUEADA] Camada técnica colapsável
- `TechnicalPerformanceSection` colapsada por padrão, com estado persistido localmente.
- **Aceite:** conteúdo permanece acessível por leitor de tela quando expandido; o colapso
  nunca esconde diagnóstico crítico.

---

## 4. Onda 4 — superfície de produto (maior valor, maior esforço)

Ordenadas por relação valor/esforço. **Todas dependem de decisão de produto.**

| Ordem | Módulo | Pré-requisito | Reviewer |
|---|---|---|---|
| 1 | **ROI / payback** | ADR-067 Etapas C, D, E — já aceitas, falta executar | **sim** (C e D) |
| 2 | **Impacto ambiental** | ADR-066 Etapa B em diante (router, contrato, card) | **sim** (endpoint) |
| 3 | **Central de alertas** | **Endpoint de leitura não existe** — exige ADR, endpoint e tela | **sim** |
| 4 | **Relatórios mensais** | Backend completo (ADR-027/028/038/039); falta a tela e o download | não |
| 5 | **Configuração da usina** | Backend completo (ADR-055/057); exige shell de configuração | **sim** |
| 6 | **Faturas pendentes** | Backend completo (ADR-035/036); fluxo hoje só por Telegram | **sim** |
| 7 | **Identidade no header** | Depende da decisão single-tenant vs. multi-usina | **sim** |

**Regra do ADR-067, a preservar:** não criar shell de configuração enquanto houver apenas
uma coisa a configurar. O shell nasce quando o item 5 ou o item 7 forem aprovados — não
antes.

---

## 5. Sequenciamento sugerido

    Aprovação do diagnóstico pelo usuário
      -> Onda 1 (etapas 1.1 a 1.7)     sem decisão pendente, ganho imediato
      -> Revisão visual humana         a auditoria não pôde ver telas
      -> Onda 2 (2.1, 2.2)             interação do gráfico
      -> Decisões da secao 5 do design usuário responde
      -> Onda 3 (só as desbloqueadas)
      -> ADR-068 (expectativa no backend), se aprovado
      -> Onda 4, item a item

**Importante:** a Onda 1 inteira pode ser executada pelo worker sem nenhuma decisão nova de
produto, e sozinha deve elevar acessibilidade, responsividade e consistência.

---

## 6. Estimativa de impacto na nota

Projeção, não promessa. Cada valor depende do aceite verificado das etapas.

| Marco | Nota geral projetada | O que muda |
|---|---:|---|
| Hoje | **7,2** | — |
| Após Onda 1 | ~**8,1** | Acessibilidade 6,5 para 8,5; responsividade 6,5 para 8,0; consistência 8,0 para 9,0; hierarquia 7,0 para 8,0 |
| Após Onda 2 | ~**8,4** | Visualização de dados 6,5 para 8,5; interação 6,5 para 8,0 |
| Após Onda 3 | ~**8,8** | Clareza 7,5 para 9,0; honestidade 8,5 para 9,5; arquitetura da informação 6,5 para 7,5 |
| Após Onda 4 (itens 1 a 4) | ~**9,4** | Arquitetura da informação 7,5 para 9,5; diferenciação 7,5 para 9,5 |

**10/10 exige, além de tudo acima, inspeção visual real com usuários reais.** Nenhuma
auditoria estática — incluindo esta — pode atribuir 10 com honestidade.
