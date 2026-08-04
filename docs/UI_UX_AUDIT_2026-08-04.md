# Auditoria de UI/UX — Mplacas

**Data:** 2026-08-04
**HEAD auditado:** `78d8aaf` (`main`, working tree limpo no início da auditoria)
**Escopo:** frontend React/TS (`frontend/src`), contratos de API consumidos, e o inventário
de endpoints de backend disponíveis mas não expostos na interface.
**Modo:** auditoria. Nenhum arquivo de produção foi alterado. Nenhum cálculo foi tocado.

---

## 0. Limitações declaradas desta auditoria

Estas limitações são declaradas antes de qualquer conclusão, porque condicionam o peso
das evidências:

1. **Não houve inspeção visual real.** O executor desta auditoria não dispõe de navegador,
   screenshot, nem ferramenta de renderização. Nenhuma tela foi vista. Toda a análise
   visual é **derivada da leitura de JSX + classes Tailwind + testes de estrutura de DOM**,
   e do cálculo aritmético das relações de contraste dos tokens reais. Onde a conclusão
   depende de pixels, isso está marcado como **hipótese**, não como problema comprovado.
2. **Não houve acesso à internet.** O benchmark competitivo (documento separado) é baseado
   em conhecimento de treinamento até meados de 2026, **explicitamente rotulado como não
   verificado ao vivo**. Nenhuma característica específica de concorrente foi inventada;
   o que não pôde ser afirmado com segurança foi omitido.
3. **A aplicação não foi executada em runtime.** `npm run type-check`, `npm run test` e
   `npm run build` foram executados de fato (resultados na seção 2). `npm run dev` não foi
   aberto em navegador.

---

## 1. Stack confirmada no código (não no README)

| Item | Valor verificado | Fonte |
|---|---|---|
| Framework | React 19.2 | `frontend/package.json` |
| Roteamento | `react-router` 8.3 | `frontend/src/App.tsx` |
| Build | Vite 8.2 + TypeScript 7.0 | `frontend/package.json`, `vite.config.ts` |
| Estilo | Tailwind CSS 4.1 via `@tailwindcss/vite` | `frontend/src/index.css` |
| Testes | Vitest 4.1 + Testing Library + jsdom | `frontend/vitest.config.ts` |
| Deploy | Cloudflare Pages (`wrangler.toml`, `public/_headers`, `public/_redirects`) | repo |
| **Dependências de runtime** | **apenas `react`, `react-dom`, `react-router`** | `package.json` |
| Biblioteca de gráficos | **nenhuma** — gráficos são SVG/`div` à mão | `ProductionHistoryChart.tsx` |
| Tipografia | `system-ui` stack, sem webfont | `index.css` |

**Confirmação explícita:** não existe nenhuma referência a Inter, Google Fonts ou CDN de
fonte no código (busca em `src/`, `index.html`, `public/` retorna apenas falsos positivos
em `pointer-events`). O resíduo do commit não autorizado `bcd2a42` foi de fato eliminado.

### Rotas existentes

Duas, e apenas duas: `/login` e `/dashboard` (`App.tsx`). Qualquer outra rota redireciona
para `/dashboard`. **Não há navegação, nem shell de aplicação, nem página secundária.**

### Endpoints efetivamente consumidos pelo frontend

- `GET /energy/executive/latest?plant_id=`
- `GET /photovoltaic/summary?plant_id=`
- `GET /energy/anomalies/latest?plant_id=&expected_daily_production_kwh=&days=90`
- `POST /auth/login`, `/auth/refresh`, `/auth/logout`

---

## 2. Saúde técnica verificada (executada, não presumida)

| Comando | Resultado |
|---|---|
| `npm run type-check` | **passa**, zero erros |
| `npm run test` | **21 arquivos, 111 testes, todos passam** (37s) |
| `npm run build` | **passa** — JS 285,99 kB (**86,11 kB gzip**), CSS 24,86 kB (5,50 kB gzip) |

Nenhuma falha preexistente foi encontrada. Nenhuma dependência foi alterada durante a
auditoria.

**Leitura:** para um dashboard analítico com gráfico interativo, 86 kB gzip é um número
muito bom — consequência direta da decisão de não adicionar biblioteca de gráficos. Isso é
um ponto forte real e deve ser preservado em qualquer proposta futura.

---

## 3. O que o redesenho recente de fato entregou (confirmado no HEAD)

Esta seção existe para **não descontar pontos por problemas já resolvidos**. Cada item
abaixo foi verificado no código do HEAD atual, não assumido a partir de mensagens de commit.

| Entrega | Evidência no HEAD |
|---|---|
| Componente-base `Card` único | `components/Card.tsx` + `Card.test.tsx` (5 testes de esqueleto/tom/acento) |
| Grid de página de 12 colunas (bento) | `DashboardPage.tsx:205` — `grid-cols-1 md:grid-cols-6 lg:grid-cols-12` |
| Hero em faixa horizontal em `lg+` | `HeroCard.tsx` — `grid-template-areas` reposicionando sem duplicar marcação |
| Container largo | `max-w-7xl 2xl:max-w-[96rem]` em `DashboardPage` **e** `DashboardHeader` (consistentes) |
| Produção esperada real (não constante) | `photovoltaic-contracts.ts::deriveExpectedDailyProduction`, a partir do baseline sazonal |
| Estado do dado honesto | `EstimatedSavingsCard` nunca renderiza R$ 0,00; `savingsUnavailableMessage`; selo "Parcial" só nos indicadores derivados do dado diário |
| Frescor real do dado | `DataFreshness` mostra a data do último dado coletado, não a hora do fetch |
| Diagnósticos com causa + ação | `DiagnosticsCard`, ordenado por gravidade, com rótulo textual de severidade |
| Distinção 404 vs 5xx | `classifyAnomalyErrorStatus` + `ProductionHistorySection` (mensagens distintas, retry só no 5xx) |
| Acessibilidade trabalhada | tab stop único no gráfico (`role="slider"` + setas), `aria-valuetext` completo, `aria-live="polite"` no painel de detalhe, `focus-visible:ring` em todos os controles, guard contra `text-gray-400` |
| Camada técnica fotovoltaica | `TechnicalPerformanceSection` (PR bruto e corrigido por temperatura, yield específico, disponibilidade de reporte, degradação, taxonomia de perdas com `evidence_level`) |
| Router PV (ADR-065) | `src/mplacas/photovoltaic/router.py` — `/summary` sempre 200, blocos ausentes como `null` + motivo |
| Tokens semânticos centralizados | `lib/dashboard/visuals.ts` — nenhuma classe `bg-red-*`/`text-green-*` crua nos componentes (garantido por teste) |

**Conclusão desta seção:** o produto **não** está no estado "amador" que motivou o
prompt-mestre. A base é sólida, disciplinada e, em alguns pontos (honestidade do dado,
taxonomia de perdas com nível de evidência), acima da média do setor. A auditoria abaixo
parte desse patamar.

---

## 4. Achados — evidência, impacto, recomendação

Classificação: **P0** bloqueante · **P1** alta · **P2** média · **P3** polimento.
Cada achado marca se é **problema comprovado**, **hipótese** ou **preferência**.

**Nenhum achado P0 foi encontrado.** Não há perda de dado, ação perigosa, quebra de
autenticação, informação financeira falsa nem interface inutilizável.

---

### P1-01 — Cálculo energético executado no frontend, contrariando o ADR-012 · *problema comprovado*

**Arquivo:** `frontend/src/lib/dashboard/photovoltaic-contracts.ts:274`

    const kwh = dcCapacityKwp * clearSkyPoaKwhM2 * performanceRatio

O ADR-012 é explícito — e o ADR-066 o cita textualmente: *"Regras e cálculos energéticos
continuam exclusivamente no backend determinístico."* Aqui o frontend multiplica capacidade
DC × POA de céu limpo P90 × PR mediano do baseline para produzir a produção diária esperada.

**Agravante:** esse número é então **enviado de volta ao servidor** como
`expected_daily_production_kwh` na query string de `/energy/anomalies/latest`
(`DashboardPage.tsx:127-128`). O cliente determina o valor de referência contra o qual o
backend classifica NORMAL/ATENÇÃO/ANOMALIA/CRÍTICO para 90 dias.

**Impacto:** violação de ADR aceito; superfície de confiança do dado; impossível auditar o
número exibido a partir do backend.
**Recomendação:** mover a derivação para o backend e devolvê-la em `/photovoltaic/summary`
como campo próprio (`expected_daily_production_kwh` + versão de modelo), no mesmo padrão
versionado de `PERFORMANCE_MODEL_VERSION`. `/energy/anomalies/latest` passa a resolver a
expectativa internamente; o parâmetro de query é depreciado.
**Esforço:** M. **Risco:** médio (muda contrato de dois endpoints).
**Critério de aceite:** `deriveExpectedDailyProduction` deixa de existir no frontend;
nenhuma chamada do frontend envia expectativa de produção ao servidor.
**PRECISA DE CONFIRMAÇÃO DO USUÁRIO** — é mudança de contrato de API em produção.

---

### P1-02 — A linha "Esperado" do gráfico é uma constante única para os 90 dias · *problema comprovado*

**Arquivos:** `src/mplacas/intelligence/anomaly_service.py:146,157` (o mesmo
`expected_daily_production_kwh` é atribuído a **todos** os dias) e
`frontend/src/components/ProductionHistoryChart.tsx:216-224` (linha tracejada por dia).

Consequências verificáveis:

1. A linha tracejada rotulada "Esperado", desenhada individualmente sobre cada barra,
   **sugere uma expectativa por dia que não existe** — é o mesmo número replicado.
2. O painel de detalhe diz `Esperado: X kWh` para um dia específico, reforçando a leitura.
3. O número mais destacado do gráfico — `Desempenho: {X}%` em `text-lg` colorido por
   severidade — é `soma(real) / soma(esperado)` sobre 90 dias contra uma constante derivada
   de **POA de céu limpo P90**. Numa janela que atravessa estações e dias nublados, a
   expectativa é sistematicamente otimista e o percentual, sistematicamente pessimista.

**Ressalva de honestidade da auditoria:** a **classificação de nível** por dia
(NORMAL/ANOMALIA/…) **não** sofre desse problema — `assess_daily_performance` recebe
`irradiation_kwh_m2` e a mediana histórica e desconta o clima
(`anomaly_service.py:137-153`). O problema está confinado à linha tracejada, ao rótulo
"Esperado" do painel de detalhe e ao percentual agregado.

**Impacto:** o indicador mais visível do gráfico pode pintar de vermelho uma usina saudável
em período nublado. Erosão direta de confiança.
**Recomendação:** (a) rotular como **"Média diária esperada (baseline sazonal)"** e
desenhar **uma única linha horizontal de referência**, não um traço por barra; (b) rotular
o agregado como **"Real vs. média esperada do período"**, com a premissa visível; ou
(c) preferencialmente, expor expectativa por dia corrigida por irradiância vinda do backend
(depende de P1-01).
**Esforço:** S para (a)+(b), M para (c). **Risco:** baixo para (a)+(b).

---

### P1-03 — Falhas de contraste WCAG 2.2 AA medidas nos tokens reais · *problema comprovado*

Relações calculadas a partir dos hex reais de `index.css` e das classes Tailwind
efetivamente usadas nos componentes:

| Par (uso real no código) | Relação | Requisito | Veredito |
|---|---:|---|---|
| `--color-success` `#16a34a` sobre branco — `SEVERITY_TEXT.success` em `text-xs` (QualityBanner, HeroCard, TrendCard, legenda) | **3,30:1** | 4,5:1 | **FALHA 1.4.3** |
| `--color-success` sobre `--color-success-light` — badge em `DiagnosticsCard`/`LossBreakdownSection` | **3,15:1** | 4,5:1 | **FALHA 1.4.3** |
| `--color-warning` `#d97706` sobre branco — selo "Parcial" (`text-[10px]`) | **3,19:1** | 4,5:1 | **FALHA 1.4.3** |
| `--color-warning` sobre `--color-warning-light` — corpo do `QualityBanner` | **3,07:1** | 4,5:1 | **FALHA 1.4.3** |
| `--color-danger` `#dc2626` sobre `--color-danger-light` — badge crítico, card `tone="danger"` | **4,41:1** | 4,5:1 | **FALHA marginal** |
| Barra de progresso `bg-success` sobre trilho `gray-100` | **2,99:1** | 3:1 | **FALHA 1.4.11** |
| Barra de progresso `bg-warning` sobre trilho `gray-100` | **2,89:1** | 3:1 | **FALHA 1.4.11** |
| Linha tracejada "Esperado" `border-gray-400` `#9ca3af` sobre branco | **2,54:1** | 3:1 | **FALHA 1.4.11** |
| `--color-brand-primary` `#1a56db` sobre branco | 6,18:1 | 4,5:1 | OK |
| `--color-danger` sobre branco | 4,83:1 | 4,5:1 | OK |
| `--color-data-secondary` `#7c3aed` sobre branco | 5,70:1 | 4,5:1 | OK |
| `gray-500` `#6b7280` sobre branco / `gray-50` | 4,83:1 / 4,63:1 | 4,5:1 | OK |
| `gray-600`, `gray-700`, `gray-900` sobre branco | 7,56 / 10,31 / 17,74:1 | 4,5:1 | OK |

**Nota importante:** o guard `colorContrast.test.tsx` proíbe `text-gray-400`, mas
**`border-gray-400` passa pelo filtro** — e é exatamente o que desenha a linha de
referência "Esperado" (`ProductionHistoryChart.tsx:139,221`), informação essencial do
gráfico.

**Impacto:** a Etapa 4 declarou "acessibilidade AA"; a medição mostra que a parte
estrutural foi feita (foco, ARIA, cor + rótulo) mas a **paleta de severidade não atende AA
em texto**. É o gap mais objetivamente demonstrável desta auditoria.
**Recomendação:** criar tokens **novos** de *texto* de severidade, sem tocar nos de
preenchimento: `--color-success-text: #15803d` (4,54:1), `--color-warning-text: #b45309`
(4,52:1), `--color-danger-text: #b91c1c` (6,29:1 sobre branco). Trocar o tracejado de
referência para `#6b7280`. **Nenhuma dessas mudanças altera cálculo ou semântica.**
**Esforço:** S. **Risco:** baixo.
**Critério de aceite:** estender `colorContrast.test.tsx` para **calcular** relações e
falhar abaixo de 4,5:1 (texto) e 3:1 (elemento gráfico), cobrindo `text-*`, `border-*` e
`bg-*` dos tokens de severidade.

---

### P1-04 — O breakpoint `md` não usa o grid: 768–1023px continua empilhado · *problema comprovado*

**Arquivo:** `DashboardPage.tsx:205-355`.

O grid é `md:grid-cols-6 lg:grid-cols-12` — mas **todas as sete seções** declaram
`md:col-span-6`, isto é, largura total. O tier `md` é, por construção, idêntico ao
empilhamento de uma coluna. A composição bento só nasce em `lg` (1024px).

**Impacto:** em iPad retrato (768×1024), tablets e janelas divididas, o dashboard continua
sendo exatamente a "pilha de cards um abaixo do outro" que motivou a reestruturação. A
crítica original do usuário **permanece verdadeira em uma faixa inteira de dispositivos**.
**Recomendação:** distribuir de fato em `md` (ex.: histórico `md:col-span-4` + real vs.
esperada `md:col-span-2`; fluxo `md:col-span-3` + diagnósticos `md:col-span-3`) e
uniformizar o tier `2xl` (hoje declarado em apenas duas seções).
**Esforço:** S. **Risco:** baixo (só classes de layout).
**Critério de aceite:** teste que afirme que em `md` pelo menos duas seções distintas
declaram span menor que a linha inteira.

---

### P1-05 — Rótulos do eixo de datas ficam fora do container que rola · *problema comprovado*

**Arquivo:** `ProductionHistoryChart.tsx` — o `<div className="mt-4 overflow-x-auto">`
fecha **antes** do `<div className="mt-1 flex justify-between text-[10px]">` que mostra
primeira/meio/última data.

As barras vivem num container com `minWidth: daily.length * 8` px (720px para 90 dias) que
rola horizontalmente. Os rótulos ficam fora dele, distribuídos com `justify-between` na
largura **visível**. Em qualquer viewport menor que a largura mínima do gráfico — 375px,
430px, e o gráfico dentro da coluna `lg:col-span-8` em 1024px — os rótulos **não
correspondem às barras** e não acompanham a rolagem.

**Impacto:** leitura temporal incorreta em telas pequenas. Mitigado (não eliminado) pelo
painel de detalhe, que mostra a data exata do dia selecionado.
**Recomendação:** mover a régua de datas para dentro do container rolável, com a mesma
`minWidth`, alinhada às posições reais das barras.
**Esforço:** S. **Risco:** baixo.

---

### P1-06 — Diagnósticos ficam abaixo da dobra, em coluna estreita · *hipótese (fundamentada)*

**Arquivo:** `DashboardPage.tsx:269-278` — `DiagnosticsCard` está na **terceira faixa** do
grid, em `lg:col-span-5`.

A ordem renderizada em `lg+` é: (1) Hero + QualityBanner; (2) Histórico (8 col) + Real vs.
esperada (4 col); (3) Fluxo (7 col) + Diagnósticos/Tendência (5 col); (4) Desempenho
técnico; (5) Energia e produção + Indicadores percentuais; (6) Financeiro.

Somando alturas declaradas (header 64px, `py-8`, Hero ~120px, QualityBanner, gráfico com
`height: 160px` mais cabeçalho, legenda e painel de detalhe ≈ 400px), **a lista de
diagnósticos — o único lugar da interface que diz o que fazer — começa depois da primeira
dobra em 1280×800 e muito depois dela em 375px.**

**Por que é hipótese:** a altura exata depende de renderização, que não pôde ser observada.
**Recomendação:** elevar um **resumo compacto de atenção** para dentro da faixa do Hero
(ex.: "2 críticos · 1 atenção", com âncora para a seção), mantendo a lista completa onde
está. Não mover a lista inteira para o topo — ela é longa e empurraria o gráfico para baixo.
**Esforço:** S. **Risco:** baixo.

---

### P1-07 — Ausência de seletor de período: a janela de 90 dias é fixa no código · *problema comprovado*

**Arquivo:** `DashboardPage.tsx:128` — `&days=90` literal.

Não há como ver 7 dias, 30 dias, o ciclo corrente ou 12 meses. O backend aceita o
parâmetro; a interface não o expõe. É a lacuna funcional mais visível em relação a qualquer
portal de monitoramento do setor.
**Impacto:** impede a pergunta "melhor ou pior que o período anterior?" em qualquer
granularidade que não seja o ciclo mensal do `TrendCard`.
**Recomendação:** grupo de botões de período (7/30/90 dias) no cabeçalho da seção de
histórico, refletido no rótulo do gráfico e no percentual agregado.
**Esforço:** S–M. **Risco:** baixo.

---

### P2-01 — Quatro cards numéricos duplicam valores já mostrados no diagrama de fluxo · *problema comprovado*

`EnergyFlowDiagram` exibe, com valor e unidade: Produção, Autoconsumo, Exportada,
Importada, Consumo. A seção "Energia e produção" (`EnergyProductionSection`) exibe os
**mesmos quatro números** de novo como `MetricCard`.

O teste da Etapa 5 (`DashboardPage.test.tsx:172`) garante apenas que os dois *gráficos*
redundantes foram removidos ("Composição da produção", "Origem do consumo") — a duplicação
**numérica** não é coberta por nenhum teste e permanece no HEAD.

**Impacto:** oito células de informação para cinco fatos; densidade sem ganho.
**Recomendação:** remover a seção "Energia e produção" e manter o diagrama de fluxo, que já
traz os mesmos números **com a relação entre eles** — que é o que os cards não dão.
Preservar o selo "Parcial" migrando-o para o diagrama.
**Esforço:** S. **Risco:** baixo. **Precisa de decisão de produto** (remove seção visível).

---

### P2-02 — A frase de "N dias seguidos abaixo do esperado" aparece duas vezes na mesma página · *problema comprovado*

`DashboardPage.tsx:243-250` e `ProductionHistoryChart.tsx:145-151` renderizam **o mesmo
texto**, na mesma cor de alerta, em seções adjacentes do grid (`lg:col-span-4` e
`lg:col-span-8`, lado a lado em `lg+`).
**Recomendação:** manter apenas dentro do gráfico e remover da seção lateral.
**Esforço:** XS. **Risco:** nenhum.

---

### P2-03 — "Autossuficiência" e "Dependência da rede" são o mesmo fato em dois cards · *problema comprovado*

`DashboardPage.tsx:301-312`. As duas métricas são complementares (somam ~100%) e recebem
duas barras de progresso azuis independentes, sugerindo dois indicadores distintos.
**Recomendação:** um único card com **uma barra 100% empilhada** (autossuprido vs.
importado) e os dois percentuais rotulados — mesma linguagem já usada no `EnergyFlowDiagram`.
**Esforço:** S.

---

### P2-04 — Seção Financeiro: oito cards uniformes misturando quatro grandezas · *problema comprovado*

`DashboardPage.tsx:322-355`, grid `lg:grid-cols-4` com: 3x R$ (total, componente energia,
iluminação pública), 1x R$ (economia), 2x R$/kWh (tarifas), 1x kWh (saldo de créditos),
1x % (cobertura).

1. **Parte/todo achatado:** componente de energia + iluminação pública **compõem** o valor
   total da fatura, mas aparecem como três cards de peso visual idêntico, sem indicar a
   relação.
2. **Grandeza fora de lugar:** "Saldo de créditos" está em kWh — é energia, não dinheiro.
3. **Falsa precisão sem hierarquia:** tarifas com 6 casas decimais (correto por ADR-056)
   recebem o mesmo destaque tipográfico que o valor total da fatura.

**Recomendação:** três blocos — *Custo do ciclo* (total, com energia e iluminação como
decomposição interna), *Economia*, *Créditos* (saldo + cobertura, que são energia). Tarifas
viram linha de apoio, não card de destaque.
**Esforço:** M. **Risco:** baixo — **nenhuma fórmula, arredondamento ou unidade muda.**

---

### P2-05 — `hover:shadow-md` em todos os cards cria falsa affordance de clique · *problema comprovado*

`Card.tsx:44` aplica `transition-shadow hover:shadow-md` incondicionalmente. Nenhum card do
dashboard é clicável. Elevação no hover é a convenção universal de "isto é interativo".
**Recomendação:** `interactive?: boolean`, aplicado só a cards que naveguem ou expandam.
**Esforço:** XS.

---

### P2-06 — Skeleton da seção técnica não tem a forma da seção que substitui · *problema comprovado*

`TechnicalPerformanceSection` usa `MetricCardSkeletonGrid count={4}` — um skeleton
desenhado para a **página inteira** (faixa full-width + bloco grande + coluna de cards
pequenos, com seu próprio `lg:grid-cols-12`), enquanto a seção real é 3 cards + 2 cards. É
ainda aninhado dentro de uma seção que já é `lg:col-span-12`.
**Impacto:** salto de layout quando `/photovoltaic/summary` responde — exatamente o que o
comentário do próprio arquivo diz querer evitar.
**Recomendação:** skeleton dedicado com a mesma malha da seção.
**Esforço:** S.

---

### P2-07 — Sessão expirada leva ao login sem explicar por quê · *problema comprovado*

`api.ts` faz logout silencioso quando o refresh falha; `DashboardPage` trata 401 com
`return` sem mensagem; `ProtectedRoute` redireciona. O usuário é ejetado para `/login` com
a tela em branco.
**Recomendação:** propagar um motivo (`?reason=session_expired`) e exibir aviso neutro na
`LoginPage`.
**Esforço:** S. **Toca auth — exige reviewer.**

---

### P2-08 — Banner de erro global sem ação de recuperação · *problema comprovado*

`DashboardPage.tsx:193-200`: quando `/energy/executive/latest` falha, a página fica
**inteiramente vazia** exceto por uma faixa vermelha. O botão "Atualizar" existe acima, mas
é um link de texto `text-xs` não associado ao erro. Contraste com a qualidade do tratamento
em `ProductionHistorySection`, que faz isso corretamente.
**Recomendação:** replicar o padrão de `ProductionHistorySection`.
**Esforço:** XS.

---

### P2-09 — Números sem `tabular-nums` em um produto de dados · *problema comprovado*

Busca por `tabular-nums`/`font-variant-numeric` em `src` retorna **zero ocorrências**.
Todos os valores usam largura proporcional de dígito. Em colunas de `MetricCard` alinhadas
verticalmente e nas linhas do `TrendCard`, os dígitos oscilam entre valores.
**Recomendação:** `tabular-nums` no valor principal do `Card`/`MetricCard`, nas linhas de
tendência e no painel de detalhe do gráfico.
**Esforço:** XS. **Ganho de percepção de precisão desproporcional ao custo.**

---

### P2-10 — Favicon aponta para um arquivo que não existe no build · *problema comprovado*

`frontend/index.html` referencia `/vite.svg`. `frontend/public/` contém apenas `_headers` e
`_redirects`; `dist/` **não contém `vite.svg`** (verificado após `npm run build`). O ícone
da aba é um 404.

Além disso: sem `meta description`, sem `theme-color`, sem manifesto, sem `apple-touch-icon`.
Para um produto que o dono da usina abre no celular, não há ícone de tela inicial.
**Recomendação:** favicon próprio (SVG + PNG), `theme-color`, `manifest.webmanifest`
mínimo, `apple-touch-icon`.
**Esforço:** S. **É o sinal de "amadorismo" mais barato de eliminar do repositório inteiro.**

---

### P2-11 — Escala tipográfica com valores arbitrários repetidos e sem tokens · *problema comprovado*

Tamanhos em uso: `text-[10px]` (5x), `text-[11px]` (4x), `text-xs`, `text-sm`, `text-lg`,
`text-xl`, `text-2xl`. Sete degraus, dois arbitrários, sem definição central. 10px está
abaixo do mínimo recomendado e é usado em conteúdo real (selo "Parcial", rótulos de eixo).
**Recomendação:** escala fechada de seis degraus tokenizada em `index.css` (`@theme`), com
piso de 12px para qualquer texto legível.
**Esforço:** M.

---

### P2-12 — Hierarquia de seção mais fraca que a hierarquia de card · *problema comprovado*

`SectionTitle` = `text-sm font-semibold text-gray-700`. O valor de qualquer `MetricCard` =
`text-2xl font-semibold text-gray-900`. O título "Dashboard executivo" (o `h2` da página) =
`text-sm font-medium text-gray-600` — **menor e mais claro que o título de uma seção
subordinada a ele**.

Resultado estrutural: a página não tem cristas visuais; é uma superfície plana de valores
grandes onde nada indica onde uma seção termina e outra começa, exceto o espaçamento.
**Recomendação:** `SectionTitle` para `text-base font-semibold text-gray-900`; remover ou
reposicionar o `h2` "Dashboard executivo" (redundante com o `h1` do header).
**Esforço:** S.

---

### P2-13 — Dias sem dado desaparecem do gráfico sem indicação · *problema comprovado*

`anomaly_service.py:132` itera `sorted(energy_by_day)` — apenas dias **com registro
persistido**. Dias sem coleta não entram no array. O gráfico desenha as barras restantes
contíguas e uniformemente espaçadas, rotulando "Histórico de produção diária (N dias)".

O rótulo é honesto quanto à contagem, mas **o eixo temporal é distorcido**: 80 dias com
dado num intervalo de 90 são renderizados como sequência contínua sem lacunas.
**Recomendação:** exibir "N de 90 dias com dado coletado" e representar lacunas como espaço
vazio no eixo.
**Esforço:** M (usa `start_date`/`end_date` já presentes no payload).

---

### P2-14 — Header sem identidade de usina, organização ou usuário · *problema comprovado*

`DashboardHeader.tsx` tem exatamente um `h1` "Mplacas — Dashboard" e um botão "Sair". A
usina exibida vem de `VITE_PLANT_ID` — uma **variável de build**. Não há nome de usina, de
organização, nem identificação do usuário logado.

Incompatível com o caminho já decidido no ADR-052 (SaaS multi-tenant) e ADR-054 (onboarding
e convites), ambos com backend implementado.
**Recomendação:** header com nome da usina (de `/plants/{id}`), organização e menu de
usuário. `VITE_PLANT_ID` como fallback, não como fonte única.
**Esforço:** M. **Toca organizations — exige reviewer.**

---

### P3-01 — `role="progressbar"` usado para composição, não para progresso

`EnergyFlowDiagram` marca as barras empilhadas de composição como `role="progressbar"`.
`progressbar` significa avanço rumo à conclusão de uma tarefa; aqui é partição de um total.
Alternativa mais correta: `role="img"` com `aria-label` completo. Impacto baixo — o
`aria-label` atual já carrega o significado.

### P3-02 — `HeroCard` poderia usar `role="meter"` para o índice de saúde

92/100 é medida, não progresso. `role="meter"` existe para isso. Prioridade baixa: suporte
de leitores de tela a `meter` é irregular.

### P3-03 — `DiagnosticsCard` define a própria margem externa

`className="mt-4"` está **dentro** do componente. Um componente não deve conhecer o
espaçamento do contexto onde é colocado — torna a composição imprevisível no reuso.

### P3-04 — `LoginPage` navega durante a renderização

`LoginPage.tsx:16-19` executa `navigate()` no corpo do render. Funciona hoje; é fonte
conhecida de aviso e de comportamento imprevisível em modo concorrente. Correção
idiomática: `Navigate to="/dashboard" replace` como elemento retornado.

### P3-05 — Sem `ErrorBoundary` e sem tela de erro para falha de ambiente

`env.ts` lança na importação se `VITE_API_URL`/`VITE_PLANT_ID` faltarem — falhar rápido é
correto, mas o resultado visível é uma **página em branco**. Idem para qualquer erro de
render: não há `ErrorBoundary` em lugar nenhum.

### P3-06 — Comentário de ordenação contradiz o código

`DashboardPage.tsx:280-287` afirma que a seção técnica vem "antes do Bloco 2". No JSX ela
vem **depois** do fluxo de energia e dos diagnósticos.

---

### Observação sem prioridade — campos de contrato parseados e nunca exibidos

`self_consumption_rate_percent` e `exported_generation_rate_percent` são validados por
`parseExecutiveDashboard` e nunca renderizados. Não é código morto (fazem parte da
validação de contrato), mas vale registrar a decisão: exibir ou documentar por que não.

### Riscos latentes (não são defeitos hoje)

- `ProductionHistoryChart` faz `toNumber(d.actual_production_kwh) ?? 0`. **Hoje isso nunca
  dispara** — `anomaly_service.py:40-41` tipa os dois campos como `Decimal` não-nulos e
  dias sem registro simplesmente não entram no array. Mas o dia em que o contrato admitir
  nulo, um dado ausente vira uma barra de zero indistinguível de produção real zero,
  violando o princípio central do projeto. Tratar `null` como lacuna, não como zero.
- `Math.max(barHeightPercent, 2)` desenha 2% de altura mínima: um dia de produção
  genuinamente zero aparece como barrinha visível. Aceitável como affordance, mas precisa
  ser decisão consciente.

---

## 5. Módulos ausentes — com evidência de que o backend já os suporta

Este é o achado mais relevante da auditoria de módulos: **a maior lacuna do Mplacas não é
estética, é de superfície de produto**. Existe um backend maduro cuja maior parte não tem
interface.

| Módulo | Endpoints já existentes | ADR | Estado no frontend |
|---|---|---|---|
| **Relatório mensal** (+ CSV/PDF/XLSX, exportação assíncrona) | `GET /reports/monthly/latest`, `.csv`, `.pdf`, `.xlsx`, `POST /reports/monthly/exports`, `GET .../{task_id}`, `.../download` | 027, 028, 038, 039 | **ausente** |
| **Faturas** (intake, pendentes, confirmar, rejeitar) | `POST /billing/intake-text`, `GET /billing/pending`, `POST /billing/{id}/confirm`, `/reject` | 035, 036, 056 | **ausente** — o fluxo hoje depende de Telegram/API |
| **Explicação assistida por IA** | `GET /explanations/latest` | 014 | **ausente** |
| **Configuração técnica da usina** | `GET`/`PATCH /plants/{id}/technical-configuration`, `PATCH /plants/{id}/location` | 055, 057 | **ausente** |
| **Estado operacional / pipeline** | `GET /operations/jobs`, `/operations/status`, `/orchestration/status/latest` | 022, 023, 029 | **ausente** |
| **Organizações, convites, usuários** | `POST/GET /organizations`, `/invitations`, `/users` | 052, 053, 054 | **ausente** |
| **Credenciais operacionais** | `POST/GET /credentials`, `/{id}/revoke` | 031, 032, 043 | **ausente** |
| **Central de alertas** | **não existe endpoint de leitura** — há ledger em banco (`alerts/sql_ledger.py`) e apenas `POST /alerts/run` | 017, 018, 040 | **ausente, e exige endpoint novo** |
| **Impacto ambiental (CO2 evitado)** | módulo puro `intelligence/environmental.py` implementado, **sem router e sem consumidor** | 066 | Etapa A feita; B+ pendentes |
| **ROI / payback** | economia já persistida no snapshot; migration do CAPEX aplicada | 067 | Etapas C/D/E pendentes |
| **Série de performance PV** | `GET /photovoltaic/performance` (série temporal) | 065 | **ausente** — só `/summary` é consumido |

**Interpretação:** o dashboard consome **3 de aproximadamente 30 endpoints**. Nenhum desses
módulos deve ser criado "para preencher menu" — mas cinco deles (relatório, faturas,
alertas, configuração da usina, ROI) resolvem perguntas que o usuário faz e que hoje ficam
sem resposta na interface.

---

## 6. Arquitetura da informação — a jornada mental é respondida?

| Pergunta do usuário | Respondida hoje? | Onde | Observação |
|---|---|---|---|
| Minha usina está funcionando? | **Sim, bem** | `HeroCard` (status + índice de saúde + headline) | Melhor elemento da interface |
| Quanto produziu? | **Sim** | "Produção no ciclo" + gráfico | |
| Quanto deveria ter produzido? | **Parcialmente** | `ExpectedProductionCard` + linha do gráfico | Comprometido por P1-02 |
| Melhor ou pior que o período anterior? | **Sim, só mês a mês** | `TrendCard` | Sem outra granularidade (P1-07) |
| Quanto consumi / importei / injetei? | **Sim, duas vezes** | `EnergyFlowDiagram` + `EnergyProductionSection` | Redundante (P2-01) |
| Quanto economizei / custou? | **Sim** | Seção Financeiro | Organização fraca (P2-04) |
| Existe problema? Qual atender primeiro? | **Sim, mas escondido** | `DiagnosticsCard`, ordenado por gravidade | Abaixo da dobra (P1-06) |
| Os dados estão completos e atualizados? | **Sim, excelente** | `QualityBanner` + `DataFreshness` + selo "Parcial" | Ponto forte diferencial |
| O que devo fazer agora? | **Sim** | `recommended_action` em cada diagnóstico | Mesma limitação de posição |
| Como está o desempenho técnico? | **Sim, com profundidade rara** | `TechnicalPerformanceSection` | PR corrigido por temperatura e taxonomia de perdas com nível de evidência estão acima do padrão do setor |
| Tenho créditos suficientes? | **Parcialmente** | "Saldo de créditos" + "Cobertura" | Sem projeção de expiração |
| **Quanto tempo até o investimento se pagar?** | **Não** | — | ADR-067, Etapas C/D/E |
| **Quanto de CO2 evitei?** | **Não** | — | ADR-066, Etapa B+ |
| **Quanto produzi hoje?** | **Não diretamente** | último ponto do gráfico | Pergunta nº 1 de qualquer portal do setor |
| **Onde estão meus relatórios / faturas?** | **Não** | — | Backend pronto |

**Veredito:** a **ordem** das seções está substancialmente correta e **não deve ser
reescrita**. As correções recomendadas são cirúrgicas: elevar o resumo de atenção (P1-06),
eliminar a redundância (P2-01), reorganizar o financeiro (P2-04). O resto da jornada é
sólido.

---

## 7. Sistema de pontuação

| Dimensão | Peso | Nota | Evidência determinante |
|---|---:|---:|---|
| Clareza e compreensão | 15% | **7,5** | Unidades sempre visíveis, motivos de indisponibilidade explícitos, nunca R$ 0,00 fabricado. Descontos: expectativa achatada (P1-02), financeiro sem hierarquia (P2-04) |
| Hierarquia visual | 12% | **7,0** | Faixa Hero bem resolvida; mas título de seção mais fraco que valor de card, `h2` menor que `h3` (P2-12) |
| Arquitetura da informação | 12% | **6,5** | Jornada correta, mas ação abaixo da dobra (P1-06) e 3 de ~30 endpoints expostos |
| Consistência do design system | 10% | **8,0** | `Card` base consolidado e testado, tokens de severidade centralizados, zero classe de cor crua. Descontos: sem tokens de tipografia/espaçamento, `text-[10px]`/`text-[11px]` |
| Visualização de dados | 10% | **6,5** | Eixo duplo honesto para irradiância, navegação por teclado, legenda textual. Descontos: régua de datas dessincronizada (P1-05), linha de referência achatada (P1-02), lacunas invisíveis (P2-13), sem seletor de período (P1-07) |
| Responsividade | 10% | **6,5** | Grid de 12 colunas real em `lg+`; mas `md` inteiro empilhado (P1-04) e `2xl` inconsistente |
| Acessibilidade | 10% | **6,5** | Trabalho estrutural genuíno (foco, ARIA, cor + rótulo, guard de regressão) anulado em parte por 8 pares de contraste reprovados e medidos (P1-03) |
| Confiança e honestidade dos dados | 8% | **8,5** | Melhor dimensão do produto. Motivos tipados, "Parcial" só onde é verdade, frescor = data do dado real. Desconto por P1-02 e P2-13 |
| Performance percebida | 5% | **8,0** | 86 kB gzip, sem lib de gráfico, skeletons presentes. Descontos: cascata de 3 requisições onde a mais lenta começa por último; skeleton técnico com forma errada (P2-06) |
| Estados de interface | 4% | **8,5** | 404 vs 5xx com mensagens distintas e retry só onde faz sentido — acima da média. Descontos: erro global sem retry (P2-08), sessão expirada muda (P2-07) |
| Qualidade de interação | 2% | **6,5** | Seleção por mouse e teclado no gráfico. Sem seletor de período, sem drill-down, sem explicação de jargão (PR, yield específico) |
| Diferenciação competitiva | 2% | **7,5** | PR corrigido por temperatura, taxonomia de perdas com `evidence_level`, baseline sazonal + degradação — acima de portais de consumidor. Faltam itens de mesa: CO2, ROI, alertas, relatórios |

### Notas consolidadas

| Recorte | Nota |
|---|---:|
| **Visual** | **7,0** |
| **Usabilidade** | **6,8** |
| **Técnica de frontend** | **8,3** |
| **Acessibilidade** | **6,5** |
| **GERAL PONDERADA** | **7,2 / 10** |

Cálculo: 7,5x0,15 + 7,0x0,12 + 6,5x0,12 + 8,0x0,10 + 6,5x0,10 + 6,5x0,10 + 6,5x0,10 +
8,5x0,08 + 8,0x0,05 + 8,5x0,04 + 6,5x0,02 + 7,5x0,02 = **7,195**.

**7,2 não é uma nota ruim.** É a nota de um produto com fundação correta, disciplina de
engenharia acima da média e três frentes objetivas de fechamento: contraste medido,
comportamento em tablet, e superfície de produto.

---

## 8. O que falta, especificamente, para 10/10

Nenhum item abaixo é estético. Cada um é verificável.

1. **Contraste AA medido, não declarado** — os 8 pares reprovados de P1-03 corrigidos, com
   teste que **calcula** a relação (não apenas proíbe uma classe).
2. **Expectativa de produção honesta** — P1-01 + P1-02: cálculo no backend, versionado, e
   rótulo que não promete uma expectativa por dia que não existe.
3. **Grid real em `md`** — P1-04. Sem isso, a crítica original sobre "cards empilhados"
   continua factualmente correta em tablet.
4. **Gráfico com eixo temporal íntegro** — P1-05 + P2-13 + P1-07.
5. **Ação no topo** — P1-06: o usuário sabe o que fazer sem rolar.
6. **Desredundância** — P2-01, P2-02, P2-03.
7. **Tokens de tipografia e espaçamento** — P2-11, com `tabular-nums` (P2-09).
8. **Superfície de produto** — pelo menos: central de alertas, relatórios, ROI (ADR-067
   C/D/E) e impacto ambiental (ADR-066 B+). Sem isso o teto competitivo é ~8,5.
9. **Identidade e escopo visíveis** — P2-14.
10. **Acabamento de casca** — P2-10: favicon, manifesto, ícone de tela inicial.

---

## 9. Riscos da remediação

| Risco | Mitigação |
|---|---|
| Mudar tokens de cor altera a semântica de severidade | Criar tokens **novos** de *texto* (`--color-*-text`), sem tocar nos de preenchimento. Nenhuma mudança de significado. |
| Mover o cálculo de expectativa para o backend muda contrato em produção | **Exige confirmação explícita do usuário.** Duas etapas: backend passa a devolver o campo; frontend migra; parâmetro de query é depreciado depois. |
| Remover a seção "Energia e produção" remove informação visível hoje | Decisão de produto, não técnica. Requer confirmação. |
| Novas páginas ampliam superfície de auth/tenancy | Toda etapa que toque organizations/billing/auth passa pelo reviewer, conforme `CLAUDE.md`. |
| Reorganizar o financeiro pode ser lido como mudança de cálculo | **Nenhuma fórmula, arredondamento ou unidade pode mudar.** Critério de aceite: testes financeiros existentes passam sem edição. |

---

## 10. Documentos relacionados

- `docs/UI_UX_COMPETITIVE_BENCHMARK_2026-08-04.md` — benchmark e matriz comparativa
- `docs/UI_UX_TARGET_DESIGN_2026-08-04.md` — arquitetura de destino e design system
- `docs/UI_UX_IMPLEMENTATION_ROADMAP_2026-08-04.md` — backlog priorizado e plano em etapas
