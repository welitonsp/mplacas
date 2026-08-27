# Comparativo visual — Mplacas × projetos equivalentes no GitHub

**Data:** 2026-08-27 · **Origem:** o dono relatou que *"as telas parecem de um sistema ruim"* comparadas
a outros projetos.

## Limitação declarada antes de qualquer conclusão

**Não vi as telas renderizadas.** Esta sessão não tem navegador nem ferramenta de captura, e o projeto
não possui regressão visual automatizada (ver a skill `visual-regression`). Tudo abaixo é inferido do
código: tokens, classes, dependências e estrutura de componentes.

Isso não invalida a análise — vários achados são estruturais e verificáveis no código —, mas significa
que **julgamento de composição, respiro e ritmo visual não está coberto aqui**. E, como se verá no
achado V-5, essa mesma cegueira é parte do problema.

## Os comparáveis escolhidos

Critério: projetos de monitoramento fotovoltaico/energia, open source, com interface própria (não
apenas Grafana), mantidos.

| Projeto | Estrelas | Stack | Por que serve de referência |
|---|---|---|---|
| [evcc](https://github.com/evcc-io/evcc) | 7.148 | Go + Vue | O mais polido do nicho; referência de acabamento |
| [emoncms](https://github.com/emoncms/emoncms) | 1.319 | PHP | Veterano, foco em séries temporais |
| [SOLECTRUS](https://github.com/solectrus/solectrus) | 162 | Ruby + Tailwind | **Escopo quase idêntico ao nosso**: produção, consumo, rede e desempenho financeiro |

SOLECTRUS é o comparável mais justo: mesmo domínio, mesmo porte, mesma stack de estilo (Tailwind).

## O que cada um usa

| | **Mplacas** | SOLECTRUS | evcc |
|---|---|---|---|
| Tipografia | `system-ui` no dashboard | Inter (variável) | própria + Bootstrap |
| Gráficos | 7 SVG próprios, **estáticos** | Chart.js + crosshair + zoom | ECharts |
| Tooltip/popover | — | Floating UI | Popper |
| Animação | transições CSS pontuais | auto-animate | countup.js |
| Ícones | lucide-react | FontAwesome | shopicons |
| **Ver a própria UI** | **nada** | Playwright | **Storybook + Playwright** |
| Orçamento de bundle | ✅ | ✅ size-limit | — |
| Dependências de runtime | **4** | ~18 | ~22 |

## O que o Mplacas faz melhor

Registrado primeiro de propósito, porque a conclusão fácil — "adotar uma biblioteca e copiar o
concorrente" — jogaria isso fora:

- **62 tokens semânticos** organizados por função (marca, superfície, texto, severidade, energia).
  Nenhum comparável tem vocabulário de cor específico do domínio como `--color-energy-solar` e
  `--color-energy-grid`.
- **Gráficos próprios, com teste unitário cada um.** Chart.js e ECharts não têm teste no seu projeto —
  são caixa-preta. Os nossos são auditáveis e honestos por construção.
- **4 dependências de runtime contra ~20.** Bundle de ~99 kB gzip com orçamento travado no CI.
- **972 testes de frontend**, muito acima do que os comparáveis mantêm.

O problema não é falta de rigor. É que **o rigor está em camadas que não aparecem na tela**.

---

## Achados

Formato conforme `.claude/skills/audit-evidence`. A coluna "natureza" aplica o critério da skill
`premium-product-ux`: separa o que ajuda o usuário a **entender ou decidir** do que é **só estética** —
a skill exige essa declaração explícita.

### V-1 · Duas tipografias desenhadas são baixadas e nenhuma chega ao dashboard · **P1**

**Evidência.** `frontend/public/fonts/` contém `manrope-{400,500,600,700}.woff2` e
`space-grotesk-{400,500}.woff2`. As declarações `@font-face` existem **apenas** em
`frontend/src/pages/public-home.css`. Já `frontend/src/index.css:58` define para todo o resto:

```css
font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

**Impacto.** A landing pública tem tipografia desenhada; o **produto** usa a fonte padrão do sistema.
Num produto de dados, `system-ui` lê como protótipo não finalizado — é o sinal isolado mais forte de
"sistema ruim", e provavelmente a maior fatia da percepção relatada. Ambos os comparáveis usam face
desenhada.

**Natureza.** Majoritariamente percepção, **mas não só**: Manrope tem numerais de altura consistente,
o que melhora leitura de coluna numérica — e o projeto já usa `tabular-nums` justamente por isso.

**Solução.** Aplicar Manrope como fonte de interface no `index.css`, reaproveitando os arquivos já
baixados. Space Grotesk pode ficar em números de destaque.

**Risco.** Baixo, e mensurável: as fontes já estão no bundle da landing. Verificar o impacto no
orçamento (o CI já falha se estourar) e conferir o CSP — as fontes são locais, `font-src 'self'`
já cobre.

---

### V-2 · Os gráficos não respondem ao mouse · **P1**

**Evidência.** `frontend/src/components/charts/` traz Gauge, BarList, Bullet, ColumnSeries,
SankeyFlow, Sparkline e StackedBar — todos SVG estático. Nenhum tem tooltip, crosshair ou hover.
SOLECTRUS carrega `chartjs-plugin-crosshair` e `chartjs-plugin-zoom`; evcc usa ECharts.

**Impacto.** Não dá para responder *"quanto exatamente foi no dia 14?"* sem sair do gráfico. Num
produto cujo propósito é auditar, gráfico que não pode ser interrogado é meia ferramenta — e o efeito
percebido é de baixo acabamento.

**Natureza.** **Decisão, não estética.** Ler o valor de um ponto específico é função, não enfeite.

**Solução.** Tooltip em hover/foco nos SVG existentes, sem trocar de biblioteca. `useChartEntrance.ts`
mostra que já há infraestrutura de interação. Trocar para Chart.js/ECharts custaria o orçamento de
bundle inteiro e jogaria fora sete componentes testados — a skill `chart-standards` exige ADR para
biblioteca nova, e com razão.

**Risco.** Médio. Tooltip precisa ser acessível por teclado (skill `accessible-charts`) e não pode
esconder o dado em tela pequena.

---

### V-3 · 46% dos cinzas não passam pelos tokens · **P2**

**Evidência.** Nos componentes e páginas: **400** usos de `var(--color-*)` contra **348** de
`text-gray-N` / `bg-gray-N` / `border-gray-N` crus do Tailwind.

**Impacto.** Duas fontes de verdade para a mesma decisão. O olho não nomeia, mas percebe: cinzas
ligeiramente diferentes entre cards vizinhos leem como desleixo. **Consistência é item explícito da
definição de "premium" deste projeto** (`premium-product-ux`).

**Natureza.** Consistência — critério declarado do projeto.

**Solução.** Migrar os 348 usos para os tokens equivalentes, em etapas por módulo, não de uma vez.

**Risco.** Baixo por mudança, alto se feito num único commit gigante — a skill exige etapas
revisáveis.

---

### V-4 · Dark mode existe pela metade, e ativá-lo hoje quebraria a tela · **P2**

**Evidência.** `frontend/src/index.css:77` define `:root[data-theme="dark"]` com paleta completa. O
comentário na linha 68 diz: *"Nada no app ainda lê/escreve `data-theme` (Fase 2/3)"*. Não há seletor
de tema.

**Impacto.** Trabalho pago e não entregue. Pior: com os 348 cinzas crus do V-3, ativar o tema escuro
hoje produziria texto cinza-claro sobre fundo cinza-claro em metade dos componentes.

**Natureza.** A skill `premium-product-ux` diz explicitamente que **dark mode obrigatório NÃO é
premium**. Portanto: **não priorizar**. Mas o V-3 é pré-requisito dele, então resolver V-3 destrava
isto de graça.

**Solução.** Fazer V-3 primeiro. Só depois avaliar o seletor, e como escolha de produto — não porque
os concorrentes têm.

**Risco.** Ativar antes do V-3 é regressão visual garantida.

---

### V-5 · Ninguém consegue ver a UI — e essa é a causa raiz · **P1**

**Evidência.** `frontend/package.json` não tem Storybook, Playwright nem ferramenta de captura. Os 972
testes de frontend verificam **comportamento** (`role`, `aria`, texto), nunca aparência. SOLECTRUS usa
Playwright; evcc usa Storybook **e** Playwright. A skill `visual-regression` do próprio projeto
reconhece a ausência.

**Impacto.** Este é o achado que explica os outros quatro. V-1, V-3 e V-4 não são erros de julgamento
estético — são coisas que **ninguém tinha como notar**, porque nada no fluxo de trabalho mostra a
tela. A qualidade visual não regride por descuido; regride por invisibilidade.

Sintoma imediato: **eu escrevi este relatório sem conseguir ver uma única tela.**

**Natureza.** Capacidade de processo, não estética. Sem isso, toda melhoria visual é feita às cegas e
volta a degradar.

**Solução.** Storybook ou Playwright com captura. Playwright é o mais barato aqui: já existe build, e
permite capturar as 4 telas do dashboard em claro/escuro e em duas larguras. Passa a existir artefato
visual revisável no PR.

**Risco.** Baixo tecnicamente. Ambos são devDependency — não entram no bundle e não violam a
`POLITICA_CUSTO_ZERO` (rodam no runner gratuito).

---

## Ordem recomendada

Por relação entre efeito percebido e esforço, não por severidade:

| # | Ação | Achado | Por que nesta posição |
|---|---|---|---|
| 1 | Aplicar Manrope no dashboard | V-1 | Maior mudança de percepção pelo menor esforço; as fontes já estão no repositório |
| 2 | Captura visual no CI | V-5 | Destrava tudo o mais e impede a regressão voltar. Fazer antes das mudanças grandes, para haver antes/depois |
| 3 | Tooltip nos gráficos | V-2 | Único achado que muda o que o usuário consegue decidir |
| 4 | Migrar cinzas para tokens | V-3 | Em etapas por módulo |
| 5 | Avaliar seletor de tema | V-4 | Só depois do 4, e como escolha de produto |

## O que NÃO fazer

Aplicando `premium-product-ux`, e listado porque são as reações naturais a "parece ruim":

1. **Não adotar biblioteca de componentes** (Bootstrap, MUI, shadcn) para "ficar igual aos outros".
   Custaria o orçamento de bundle e jogaria fora 53 componentes e 972 testes. O acabamento dos
   comparáveis não vem da biblioteca — vem de tipografia, interação e consistência, que são
   endereçáveis sem ela.
2. **Não trocar os gráficos por Chart.js/ECharts.** São sete componentes SVG testados, honestos e
   baratos. O que falta neles é tooltip, não motor de renderização. A skill `chart-standards` exige
   ADR para biblioteca nova.
3. **Não adicionar glassmorphism, gradiente ou sombra pesada.** A skill lista isso explicitamente como
   o que "premium" **não** é. A distância para os comparáveis não é de efeito visual.
4. **Não copiar o layout do evcc.** Usar como referência de princípio — interação em gráfico,
   tipografia desenhada —, nunca de tela.
5. **Não fazer redesenho monolítico.** A skill exige etapas pequenas revisáveis.

## Conclusão

A percepção do dono está correta, mas o diagnóstico natural — *"falta capricho visual"* — não é o que
o código mostra. O projeto tem **mais rigor** que os comparáveis em tokens, testes e orçamento; o que
falta são **três coisas concretas e delimitadas**: a tipografia que já está no repositório e não é
usada, interação nos gráficos, e consistência nos cinzas.

E as três sobreviveram porque **nada no fluxo de trabalho mostra a tela para alguém**.
