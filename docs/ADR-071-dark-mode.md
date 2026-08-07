# ADR-071 — Dark mode (tema escuro opcional, tokens em duas camadas)

## Status

Aceito (2026-08-07).

## Contexto

A skill `design-system` (`.claude/skills/design-system/SKILL.md:23`) e a skill `frontend-design`
(`.claude/skills/frontend-design/SKILL.md`, seção "Dark mode") registram que o tema único claro é o
padrão do projeto e que dark mode, se pedido, é feature nova com ADR — não parte de manutenção do
design system. O usuário pediu dark mode explicitamente. Este ADR é essa decisão de desenho; nenhum
código foi alterado para produzi-lo.

### Estado real do frontend hoje (verificado nesta sessão, não suposto)

- **Nenhuma infraestrutura de tema existe.** `Grep` por `prefers-color-scheme`, `data-theme`,
  `ThemeContext`, `useTheme` em `frontend/src/**` não encontra nenhuma ocorrência. É greenfield.
- **`frontend/src/index.css`** define 19 tokens semânticos em `:root` (marca, superfície, texto,
  severidade com par preenchimento/`-text`, gráfico, `data-secondary`) — listados na íntegra na
  seção "Decisão 4" abaixo, com o valor exato hoje.
- **Tailwind v4 (`@tailwindcss/vite`) gera TODA a paleta padrão como variáveis CSS**, não como hex
  literal nas classes. Confirmado inspecionando `dist/assets/index-*.css` após `npm run build`:
  ```css
  @layer theme{:root,:host{--color-gray-50:oklch(98.5% .002 247.839); ... --color-gray-900:oklch(21% .034 264.665); --color-white:#fff; ...}}
  .text-gray-500{color:var(--color-gray-500)}
  .bg-white{background-color:var(--color-white)}
  ```
  Isso significa que `text-gray-500`, `bg-gray-100`, `fill-gray-900` etc. **também** podem ser
  redefinidos por tema, do mesmo jeito que os 19 tokens do projeto — não é preciso limitar a
  estratégia aos tokens customizados.
- **191 ocorrências de classes `gray-*` cruas** (não tokens do projeto) em 39 arquivos de
  `frontend/src` (`Grep` contabilizado nesta sessão), incluindo dentro das 6 primitivas de gráfico
  em `frontend/src/components/charts/` (`fill-gray-500`/`fill-gray-900` em `SankeyFlow.tsx`,
  `text-gray-500`/`text-gray-400` em `Gauge.tsx`/`BarList.tsx`/`Bullet.tsx`/`StackedBar.tsx`). As
  10 paradas da escala (`gray-50` a `gray-900`) estão todas em uso em algum ponto do app.
- **Achado que muda o desenho do "sem tocar componente": `bg-white` literal em vez de
  `var(--color-surface)` no componente-base de card.** `Card.tsx` (`frontend/src/components/Card.tsx:42`,
  o esqueleto único de card documentado em `frontend-design`) usa `bg-white border-[var(--color-border)]`
  para o tom `neutral`, não `bg-[var(--color-surface)]` — apesar de `--color-surface` já valer
  `#ffffff`, o mesmo hex. O mesmo padrão aparece em `AppHeader.tsx` (header e menu dropdown),
  `AppShell.tsx` (skip-link), `main.tsx`/`ErrorBoundary.tsx` (card de erro fatal), `PlantSelector.tsx`
  (dropdown) e duas divs inline em `DashboardPage.tsx` (linhas 279 e 485). Como a estratégia de
  token deste ADR **não** redefine `--color-white` globalmente (ver Decisão 3, motivo abaixo), esses
  sete pontos precisam trocar `bg-white` por `bg-[var(--color-surface)]` — sem essa troca pontual, o
  card mais usado do app inteiro continuaria branco puro no tema escuro.
- **`LoginPage.tsx` já é uma página fixa escura, fora do sistema de tokens, com testes já quebrados
  hoje.** É um "hero" com `bg-slate-950`, gradientes `blue-600`/`indigo-600`/`cyan-400`, glassmorphism
  e `focus:ring-blue-500` — nenhum uso de `var(--color-*)`. Rodei `npx vitest run
  src/pages/LoginPage.test.tsx` nesta sessão: **4 de 7 testes falham**, incluindo as duas asserções
  que checam "usa `var(--color-brand-primary)`, não `bg-blue-*`/`focus:ring-blue-*`"
  (`LoginPage.test.tsx:27-45`), o toggle de mostrar/ocultar senha sem `aria-pressed`, e o campo de
  erro sem `aria-describedby`/`aria-invalid`. **Isto é pré-existente, não causado por este ADR** —
  descoberto ao rodar a suíte de testes como parte da due diligence deste documento. Está fora do
  escopo de dark mode (ver "Riscos e fora de escopo"), mas precisa ser sinalizado separadamente ao
  usuário porque `npm run test` já está vermelho em `main` antes de qualquer mudança deste ADR.
- **Dois hex literais fora de qualquer token** nas primitivas de gráfico: `Bullet.tsx:7`
  (`TARGET_TICK_COLOR = '#111827'`, o hex clássico do Tailwind v3 `gray-900`) e `Sparkline.tsx:13`
  (`AXIS_COLOR = '#9ca3af'`, hex clássico do `gray-400`). Um terceiro, `GRID_HEX = '#d1d5db'`
  (`lib/dashboard/visuals.ts:136`), não tem mais nenhum uso em JSX (`Grep` só encontra a própria
  declaração e um comentário) — aparenta ser código morto, não bloqueia este ADR.
- **CSP em produção bloqueia o padrão clássico de bootstrap de tema.** `frontend/public/_headers`
  declara `script-src 'self'` — sem `'unsafe-inline'` e sem nonce. O padrão mais comum de evitar
  FOUC (flash of wrong theme) é um `<script>` inline no `<head>` de `index.html` que roda antes do
  primeiro paint; com este CSP, esse script simplesmente não executa. Isso é decidido explicitamente
  na Decisão 2.
- **Drift já existente entre `index.css` e o espelho manual de teste.**
  `frontend/src/test/contrastRatio.test.ts` declara no comentário (linhas 8-19) que espelha
  literalmente os hex de `index.css` porque o Vitest mocka import `?raw` de `.css`. Mas
  `TOKENS['--color-chart-reference']` no teste é `'#6b7280'`, enquanto `index.css:35` tem
  `--color-chart-reference: #64748b`. Os dois hex são próximos (ambos cinza-azulado médio) e o teste
  ainda passa porque a diferença não muda se o par cruza o limiar de 3:1/4.5:1 — mas é uma deriva
  real entre o token declarado e o que o teste afirma verificar. Relevante aqui porque dark mode está
  prestes a **dobrar** o número de cópias manuais de hex nesse padrão; ver Decisão 7.
- **Orçamento de bundle**: rodei `npm run build` nesta sessão. Total gzip atual:
  `index-*.css` 8.56 kB + `ErrorBoundary` 0.71 kB + `App` 35.44 kB + `index` (vendor+app) 61.16 kB =
  **105.87 kB gzip**, em linha com o "~103 kB" citado na tarefa (pequena variação por commits
  recentes). Custo estimado do dark mode: ver Decisão 8 / Consequências.

## Decisão

### 1. Mecanismo de troca de tema: SO como padrão inicial + override manual persistido

**Decisão**: no primeiro acesso (sem preferência salva), o tema segue
`matchMedia('(prefers-color-scheme: dark)')`. O usuário pode sobrepor explicitamente via um
controle de UI (Decisão 6); a escolha explícita persiste em `localStorage` sob a chave
**`mplacas:theme`**, com valores literais `'light'` ou `'dark'`. **Ausência da chave** = segue o SO
(inclui reagir a mudança de preferência do SO em tempo real via `matchMedia(...).addEventListener('change', ...)`,
só enquanto não houver override salvo). Selecionar "Sistema" no controle remove a chave
(`localStorage.removeItem('mplacas:theme')`) em vez de gravar um terceiro valor — minimiza o que é
persistido, mesmo espírito de só gravar preferência não sensível já usado por
`mplacas:technical-performance-expanded`.

**Alternativas descartadas**:
- **Só `prefers-color-scheme`, sem controle manual**: rejeitada — usuário sem controle sobre o
  próprio SO (ex: notebook corporativo travado em claro) fica sem opção de usar o tema escuro que
  pediu.
- **Só toggle manual, padrão claro fixo**: rejeitada — ignora a preferência do SO no primeiro
  acesso, pior primeira impressão para quem já usa o SO em modo escuro, e é exatamente o
  comportamento que o padrão de mercado (GitHub, Linear, Vercel) evita.

**Ação de conformidade obrigatória**: `tests/test_frontend_auth_contract.py` tem allowlist explícita
de chaves de `localStorage` (`_ALLOWED_KEYS`, linhas 27-36). `mplacas:theme` precisa de uma entrada
nova ali, com o mesmo formato das duas existentes (chave + motivo textual), antes de o código de
implementação poder chamar `localStorage.setItem('mplacas:theme', ...)` sem quebrar o teste.

### 2. Como o tema chega ao DOM antes do paint — e por que não um `<script>` inline no `<head>`

**Decisão**: a resolução do tema inicial roda em `frontend/src/lib/theme.ts` (módulo novo, sem
dependência externa), chamada na primeira linha executável de `frontend/src/main.tsx`, antes de
`ReactDOM.createRoot(...).render(...)`. Ela lê `localStorage.getItem('mplacas:theme')`, cai para
`matchMedia('(prefers-color-scheme: dark)').matches` se ausente/inválida, e define
`document.documentElement.dataset.theme = 'light' | 'dark'`.

**Por que não o padrão clássico de script inline no `<head>`**: seria a forma mais comum de evitar
qualquer flash, mas `frontend/public/_headers` já declara `script-src 'self'` sem
`'unsafe-inline'`/nonce (ver Contexto) — um `<script>` inline simplesmente não executaria, silenciando
o bootstrap de tema sem erro visível ao usuário. A alternativa tecnicamente viável é adicionar um hash
`'sha256-<hash-do-script-exato>'` ao `script-src` (funciona com `_headers` estático porque o hash é
fixo em build-time, ao contrário de um nonce, que precisa variar por resposta). **Este ADR não adota
essa alternativa agora**: mudar `_headers` é uma mudança de postura de segurança que merece revisão
dedicada (mesma régua de `reviewer` que o projeto já aplica a CSP/headers), e o ganho é evitar um
flash que, nesta SPA, é no máximo o `background-color` do `<body>` piscando por uma fração de segundo
antes do módulo `main.tsx` rodar — não há HTML servido pelo backend para piscar por cima, `#root`
começa vazio. **Trade-off aceito conscientemente** (ver Consequências/Negativas), com o caminho de
reversão para a Opção B (hash CSP) documentado caso a Fase 4 (verificação visual) mostre um flash
perceptível na prática.

### 3. Estratégia de tokens: duas camadas de variáveis CSS, sem tocar componente nenhum

**Decisão**: `index.css` ganha um segundo bloco de custom properties, fora de qualquer `@layer`
(mesmo nível de `:root` hoje), selecionado por `:root[data-theme="dark"]`:

```css
:root[data-theme="dark"] {
  /* os 19 tokens semânticos do projeto, com valor escuro (Decisão 4) */
  /* + --color-gray-50 até --color-gray-900 (Decisão 4), porque 191 usos crus dependem deles */
}
```

Duas garantias de especificidade/cascata, verificadas nesta sessão inspecionando o CSS compilado:

1. **`@layer theme` (onde o Tailwind v4 declara sua paleta padrão) sempre perde para regras fora de
   `@layer`**, independente da ordem de declaração no arquivo — regra da cascata de CSS layers. Como
   o `:root[data-theme="dark"]` novo fica fora de `@layer`, ele sobrepõe
   `@layer theme{:root,:host{--color-gray-500:...}}` sem precisar de `!important`.
2. **`:root[data-theme="dark"]` (especificidade 0,1,1,0) sobrepõe o `:root` claro do próprio projeto
   (0,1,0,0)** pela mesma razão que um seletor com atributo sempre vence um sem, com ou sem depender
   de ordem de declaração.

Consequência prática: **nenhum componente precisa de lógica condicional de tema.** Um componente que
já usa `var(--color-text-primary)` ou a classe `text-gray-500` continua com o mesmo código-fonte;
só o valor resolvido da variável muda com o atributo `data-theme` no `<html>`.

**O que este ADR delibera NÃO redefinir**, e por quê:

- **`--color-white`/`--color-black`**: ficam intocados. São usados para "branco/preto literal
  independente de tema" (ex.: texto branco sobre botão de cor sólida `bg-[var(--color-brand-primary)]`)
  — se `--color-white` mudasse de valor no escuro, esse texto perderia contraste contra o próprio
  botão, que continua com a mesma cor de marca nos dois temas.
- **`--color-slate-*`**: usados quase exclusivamente dentro de `LoginPage.tsx` (já fora de escopo,
  ver Contexto) mais um único uso solto, `text-slate-800` em `SectionTitle.tsx:14`. Redefinir a
  escala `slate` inteira só para cobrir um componente re-tingiria de brinde o hero fixo do login, que
  deve continuar exatamente igual independente de `data-theme`. Solução mais barata e sem
  efeito colateral: migrar o único uso legítimo (`SectionTitle.tsx`) de `text-slate-800` para
  `text-gray-800` (que passa a responder ao tema pela Decisão 4) — feito na Fase 0.
- **`--color-blue-*`/`--color-indigo-*`/`--color-cyan-*`/`--color-rose-*`**: usados só dentro de
  `LoginPage.tsx`. Fora de escopo pelo mesmo motivo.

**Pré-requisito de normalização (Fase 0, antes de Fase 1 ter efeito visual)**: como
`--color-white` não muda, todo lugar que usa `bg-white` para representar a **superfície** do
design system (não "branco literal proposital") precisa apontar para `bg-[var(--color-surface)]`
em vez de `bg-white` — mesmo valor hoje (`#ffffff` == `--color-surface`), zero mudança visual no
tema claro, mas pré-condição para o dark mode realmente pintar essas superfícies. Lista concreta
(seção Contexto já levantou os arquivos): `Card.tsx:42`, `AppHeader.tsx:43,77`, `AppShell.tsx:14`,
`main.tsx:20`, `ErrorBoundary.tsx:30`, `PlantSelector.tsx:33`, `DashboardPage.tsx:279,485`.
`Card.test.tsx:12,45` afirma `bg-white` no className — precisa virar
`bg-\[var\(--color-surface\)\]` (regex) junto da troca, senão quebra.

### 4. Paleta escura concreta, com contraste calculado (fórmula WCAG 2.x, luminância relativa)

Mesma fórmula usada em `frontend/src/test/contrastRatio.test.ts` (luminância relativa por canal,
`(L1+0.05)/(L2+0.05)`), calculada nesta sessão para cada par crítico. Fundo de referência para os
tokens "de texto"/gráfico é `--color-surface` escuro (`#111a2b`), por ser o fundo mais comum onde
esses tokens aparecem (cards); pares contra `--color-surface-subtle` (fundo de página) também
medidos porque texto secundário aparece diretamente sobre a página em alguns pontos (ex.: rodapé de
seção).

| Token | Claro (hoje) | Escuro (proposto) | Contraste claro | Contraste escuro |
|---|---|---|---|---|
| `--color-surface-subtle` | `#f8fafc` | `#0a0f1c` | — | — |
| `--color-surface` | `#ffffff` | `#111a2b` | — | superfície vs página: **1.10:1** (elevação sutil, mesma ordem de grandeza da relação claro/hoje, ver nota abaixo) |
| `--color-border` | `#e2e8f0` | `#2a3648` | 1.23:1 vs surface (decorativo, não carrega significado sozinho) | 1.43:1 vs surface |
| `--color-text-primary` | `#0f172a` | `#eef1f7` | 17.85:1 vs surface | **15.38:1** vs surface / **16.90:1** vs surface-subtle |
| `--color-text-secondary` | `#475569` | `#9aa7bc` | 7.58:1 vs surface | **7.15:1** vs surface / **7.86:1** vs surface-subtle |
| `--color-brand-primary` | `#2563eb` | `#5b8def` | 5.17:1 vs surface (usado como texto de link) | **5.39:1** vs surface |
| `--color-brand-primary-dark` (estado hover) | `#1d4ed8` | `#8fb8ff` | — | **8.68:1** vs surface |
| `--color-brand-primary-light` (fundo do avatar) | `#eff6ff` | `#132038` | brand-primary vs brand-primary-light: 4.99:1 | brand-primary vs brand-primary-light: **5.03:1** |
| `--color-chart-reference` | `#64748b` | `#8291a8` | 4.76:1 vs surface | **5.44:1** vs surface |
| `--color-chart-track` | `#e2e8f0` | `#263144` | — (trilho, não é o elemento com significado) | — |
| `--color-data-secondary` | `#7c3aed` | `#c4b5fd` | 5.70:1 vs surface | **9.43:1** vs surface |
| `--color-data-secondary-light` | `#f5f3ff` | `#1e1b33` | data-secondary vs -light: — | data-secondary vs -light: **9.03:1** |
| `--color-gray-50`…`--color-gray-900` | oklch do Tailwind (ver Contexto) | `#0d1420` … `#f3f5f9` (10 paradas, tabela completa abaixo) | — | ver Decisão 3 nota de cobertura |

**Nota sobre `surface` vs `surface-subtle`**: no tema claro, o cartão (`surface`, branco) é **mais
claro** que a página (`surface-subtle`, cinza muito sutil) — o cartão "sobe" visualmente. O tema
escuro preserva essa mesma relação direcional: `surface` (`#111a2b`) é mais claro que
`surface-subtle` (`#0a0f1c`), não o inverso. O contraste numérico entre os dois (1.10:1 escuro vs.
~1.05:1 claro, calculado à parte) é baixo nos dois temas porque essa relação **não** é a que carrega
significado textual — é resolvida junto com `--color-border` (decorativo) para dar a impressão de
elevação, o mesmo mecanismo que o tema claro já usa hoje.

**Escala `gray-*` completa** (cobre as 191 ocorrências crua identificadas no Contexto — texto,
fundo, borda, preenchimento SVG de `fill-gray-*`):

| Parada | Escuro | Contraste vs `--color-surface` escuro |
|---|---|---|
| `gray-50` | `#0d1420` | 1.06:1 (fundo, ex. `bg-gray-50` hover de item de menu) |
| `gray-100` | `#161f30` | 1.05:1 (fundo de badge neutro) |
| `gray-200` | `#212c40` | 1.24:1 (borda) |
| `gray-300` | `#3a4760` | 1.87:1 (borda mais forte, divisor) |
| `gray-400` | `#78839a` | 4.57:1 (**não usado como texto de corpo** — `colorContrast.test.tsx` já bane `text-gray-400`, ver Decisão 7) |
| `gray-500` | `#93a0b5` | 6.58:1 (rótulo secundário) |
| `gray-600` | `#b7c1d1` | 9.58:1 |
| `gray-700` | `#d3dae5` | 12.37:1 |
| `gray-800` | `#e6eaf1` | 14.43:1 |
| `gray-900` | `#f3f5f9` | 15.95:1 (texto quase-primário, ex. `text-gray-900`/`fill-gray-900`) |

Todos os pares texto/gráfico relevantes (`text-primary`, `text-secondary`, os três `-text` de
severidade — Decisão 5 —, `chart-reference`, `data-secondary`, `brand-primary`, `gray-400` até
`gray-900`) ficam **acima de 4.5:1** (texto) ou **3:1** (gráfico) contra `--color-surface` escuro.
Nenhum deles regride abaixo do que o tema claro já garante hoje.

### 5. Severidade no escuro: separar o tom de PREENCHIMENTO do tom de TEXTO, mais que no claro

Verde/âmbar/vermelho "de livro" (`#16a34a`/`#d97706`/`#dc2626`, os tokens de preenchimento atuais)
ficam sub-saturados e às vezes ilegíveis como texto sobre fundo escuro — o mesmo motivo que já levou
o projeto a criar os tokens `-text` para o tema claro (ver comentário em `index.css:19-25`,
P1-03). No escuro esse efeito é mais forte: cores escuras/médias como `#16a34a` perdem contraste
justamente porque o fundo também é escuro (dois tons próximos em luminância).

**Decisão**: manter a mesma separação preenchimento/`-text` já estabelecida, com dois ajustes por
tema:

- **Tokens `-text`** (usados como `color`/`text-*`) ficam **mais claros e saturados** no escuro:
  `success-text: #4ade80` (verde-400), `warning-text: #fbbf24` (âmbar-400), `danger-text: #f87171`
  (vermelho-400) — contraste 9.66:1 / 10.09:1 / 6.09:1 contra `surface` escuro (todos folgados acima
  de 4.5:1).
- **Tokens de preenchimento** (`success`/`warning`/`danger`, usados em badge/barra/borda-esquerda,
  nunca como `color` de texto — mesma regra do claro) ficam num tom **médio-saturado**, não tão
  escuro quanto o claro nem tão claro quanto o `-text`: `success: #22c55e`, `warning: #f59e0b`,
  `danger: #ef4444` — ainda ≥ 4.5:1 contra `surface` escuro (7.64:1 / 8.10:1 / 4.63:1), folga
  também usada por `SEVERITY_BAR`/`SEVERITY_DOT` (`lib/dashboard/visuals.ts`) que os usa como
  preenchimento sólido de barra/ponto — precisa continuar visível como bloco de cor.
- **Fundos `-light`** deixam de ser "quase branco" e passam a ser um **tingido escuro muito sutil**
  da própria cor (`success-light: #0f2417`, `warning-light: #271b0a`, `danger-light: #2a1414`,
  `data-secondary-light: #1e1b33`) — texto `-text` sobre o próprio `-light` continua ≥ 4.5:1 (9.38:1
  / 10.08:1 / 6.28:1 / 9.03:1), preservando o padrão de badge "texto colorido sobre fundo claro/tingido
  da mesma cor" que `SEVERITY_BG`+`SEVERITY_TEXT` já usa, só invertendo a direção da luminosidade do
  fundo.

Nenhuma mudança de **semântica** de severidade (o que é `success`/`warning`/`danger` continua vindo
do backend, ver `statusMeta`/`performanceSeverity`/`levelSeverity` em `visuals.ts`) — só os hex por
tema.

### 6. Controle de UI: seletor de três estados no menu já existente do `AppHeader`

Controle "Aparência" com três opções (Sistema / Claro / Escuro) dentro do menu suspenso que já existe
em `AppHeader.tsx` (o mesmo que hoje só tem "Sair", ver `AppHeader.tsx:77-91`) — não cria superfície
de navegação nova. "Sistema" é o estado default e corresponde a "nenhuma chave em `localStorage`"
(Decisão 1). Requisitos de acessibilidade (checklist `wcag-aa`): nome acessível em cada opção (texto
visível, não só ícone), estado atual exposto via `aria-current`/equivalente de grupo de rádio,
navegável só por teclado, mesmo padrão de foco visível já usado no resto do header
(`focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]`, já confirmado presente em
`AppHeader.tsx:60,91`).

### 7. Evolução dos testes de contraste

Dois arquivos, dois tratamentos diferentes:

- **`colorContrast.test.tsx`** (bane classes `text-gray-400`/`border-gray-400`/`placeholder-gray-400`
  por nome, não por valor calculado) **não precisa virar theme-aware**: a regra "nunca use
  `gray-400` para texto" continua válida nos dois temas mesmo que o `gray-400` escuro calculado
  (4.57:1) tecnicamente passasse — manter a proibição simples e única evita ensinar o teste a
  raciocinar sobre tema, e a régua "nunca essa classe, ponto" é mais fácil de auditar do que "essa
  classe é proibida só no claro". **Correção necessária, independente de tema**: o glob
  `import.meta.glob('./*.tsx', ...)` (`colorContrast.test.tsx:10`) não é recursivo — não alcança
  `frontend/src/components/charts/*.tsx`. É por isso que `Bullet.tsx:122`
  (`text-gray-400` nos rótulos de eixo "0"/valor máximo, com `aria-hidden="true"` mas visível a
  usuários videntes) nunca foi pego por este teste. Corrigido junto deste ADR (Fase 0): trocar o glob
  para alcançar `./**/*.tsx` (ou somar um glob de `./charts/*.tsx`), e trocar o próprio
  `text-gray-400` de `Bullet.tsx` para `text-gray-500` (a régua que o teste, uma vez corrigido, passa
  a exigir).
- **`frontend/src/test/contrastRatio.test.ts`** (calcula a razão de verdade a partir de hex
  hardcoded, porque o Vitest mocka import `?raw` de `.css`) **precisa cobrir os dois temas sem
  duplicar a lógica de asserção**. Decisão: extrair os hex para um fixture novo,
  `frontend/src/test/designTokens.ts`, exportando `LIGHT_TOKENS`/`DARK_TOKENS` (mapas nome → hex,
  mesmos nomes de variável do `index.css`, incluindo os dois fundos de superfície). O teste passa a
  iterar `describe.each([['light', LIGHT_TOKENS, LIGHT_BG], ['dark', DARK_TOKENS, DARK_BG]])`,
  reaproveitando as mesmas funções `hexToRgb`/`contrastRatio` já escritas ali — mesmo padrão de
  `it.each` que `colorContrast.test.tsx` já usa para arquivo. Isso também **fecha, por construção**,
  a deriva já encontrada (`--color-chart-reference` `#6b7280` no teste vs. `#64748b` em `index.css`,
  ver Contexto): passa a existir uma única cópia manual por tema, não duas fontes divergentes.

### 8. Plano de implementação em etapas verificáveis

**Fase 0 — normalização, sem efeito visual no tema claro.** `bg-white` → `bg-[var(--color-surface)]`
nos 7 pontos listados na Decisão 3; `text-slate-800` → `text-gray-800` em `SectionTitle.tsx`;
`TARGET_TICK_COLOR`/`AXIS_COLOR` (`Bullet.tsx`/`Sparkline.tsx`) → `'var(--color-gray-900)'`/
`'var(--color-gray-400)'`; glob recursivo + fix de `text-gray-400` em `colorContrast.test.tsx`/
`Bullet.tsx` (Decisão 7); `Card.test.tsx` atualizado para a nova classe. **Prova**: `npm run
type-check` e `npm run test` verdes, `git diff` mostrando só troca de literal por token (nenhum hex
novo introduzido), nenhuma captura de tela muda (mesmo valor de cor). Toca componentes
compartilhados amplos (`Card`, `AppHeader`, `AppShell`, `ErrorBoundary`, `PlantSelector`,
`DashboardPage`) — não se enquadra na lista de billing/auth/credentials/organizations/audit/migrations
do `CLAUDE.md`, então `reviewer` não é obrigatório pela regra, mas **recomendado** dado o raio de
alcance.

**Fase 1 — tokens CSS (aditivo, zero comportamento novo).** Bloco `:root[data-theme="dark"]` em
`index.css` com os 19 tokens semânticos + `--color-gray-50..900` da Decisão 4/5. Nada no app lê
`data-theme` ainda, então o app continua idêntico visualmente. **Prova**: `npm run build` e grep do
bloco no CSS gerado (`dist/assets/*.css`) — mesma checagem que a skill `frontend-design` já manda
fazer para classe Tailwind nova; fixture `designTokens.ts` + `contrastRatio.test.ts` estendido
(Decisão 7) verde, cobrindo os pares da tabela da Decisão 4/5.

**Fase 2 — mecanismo de resolução de tema (sem toggle de UI ainda).**
`frontend/src/lib/theme.ts` (`resolveInitialTheme()`, aplica `document.documentElement.dataset.theme`
em `main.tsx`, ver Decisão 2); entrada `mplacas:theme` na allowlist de
`tests/test_frontend_auth_contract.py` (Decisão 1). **Prova**: teste unitário de
`resolveInitialTheme()` cobrindo as três ramificações (override salvo vence; ausência de override
segue `matchMedia`; valor salvo inválido é ignorado e cai no `matchMedia`); `pytest
tests/test_frontend_auth_contract.py` verde com a chave nova. Sem mudança de header/CSP nesta fase
(Decisão 2, Opção A) — não exige `reviewer` pela regra do `CLAUDE.md`.

**Fase 3 — controle de UI.** Seletor de três estados no menu do `AppHeader` (Decisão 6), persistindo/
removendo `mplacas:theme`, reagindo a `matchMedia` em modo "Sistema". **Prova**: teste de
Testing Library clicando cada opção e verificando `document.documentElement.dataset.theme` +
`localStorage`; teste de teclado (Tab/Enter) e de `focus-visible:ring`.

**Fase 4 — varredura de verificação no app inteiro em tema escuro.** Percorrer visualmente
`DashboardPage` e todas as seções/cards, as 6 primitivas de gráfico, formulários
(`CapexRegistrationForm`), skeletons, estados vazio/erro. Confirmar `colorContrast.test.tsx`
(glob corrigido) continua verde e que nenhum hex novo foi introduzido fora de `index.css`
(`Grep` por `#[0-9a-fA-F]{3,6}` em `.tsx` deve só encontrar os casos já conhecidos e aceitos, ex.
`rgba(0,0,0,...)` de sombra). `LoginPage` fica **fora** desta varredura (Decisão 3, Riscos). Por
fechar um domínio de produto inteiro (dark mode ponta a ponta), esta fase pede `quality-gate-reviewer`,
seguindo a orientação do `CLAUDE.md` para fases maiores de produto — não é uma mudança de
billing/auth/credentials/organizations/audit/migrations que tornaria `reviewer` obrigatório pela
regra, mas o `quality-gate-reviewer` é o papel certo para o checklist mais amplo de produto.

### 9. Bundle: custo estimado

- CSS: bloco `:root[data-theme="dark"]` com ~29 declarações (19 tokens semânticos + 10 paradas de
  `gray-*`) — texto altamente repetitivo (nomes de variável + hex curtos), historicamente comprime
  muito bem em gzip; estimativa **< 0.5 kB gzip** adicionados aos 8.56 kB atuais de CSS.
- JS: `lib/theme.ts` (~15-20 linhas) + o controle de UI no `AppHeader` (~30-50 linhas JSX) — sem
  nenhuma dependência nova. Estimativa **< 1 kB gzip** adicionado ao bundle de app (61.16 kB hoje).
- **Total estimado: bem abaixo de 2 kB gzip**, sobre um total atual de 105.87 kB gzip — confirma a
  premissa da tarefa de que o custo de dark mode via variáveis CSS é quase nulo. Nenhuma biblioteca
  nova (nem de tema, nem de UI) é necessária ou proposta.

## Consequências

### Positivas

- Nenhum componente precisa de `if (theme === 'dark')` — a cascata CSS resolve tudo, confirmado
  pela leitura das 6 primitivas de gráfico (todas já usam `var(--color-*)`, nenhuma cor hardcoded
  além das duas corrigidas na Fase 0).
- O trabalho de Fase 0 (tirar `bg-white` solto do componente-base `Card`) é uma correção de dívida
  do design system que vale por si só, independente de dark mode — hoje `Card.tsx` já viola a regra
  "usar o token, não o hex/classe solta" da skill `visual-tokens`.
- A extração de `designTokens.ts` (Decisão 7) fecha por construção uma deriva de teste que já existia
  antes deste ADR.
- Custo de bundle desprezível (Decisão 9).

### Negativas

- **Aceita-se um flash cosmético possível na primeira pintura** para usuários cujo tema resolvido é
  escuro (Decisão 2, Opção A) — não corrigido com mudança de CSP nesta primeira entrega. Caminho de
  reversão documentado (hash CSP, Opção B) caso a Fase 4 mostre que é perceptível na prática.
- **Sombras dos cards ficam quase invisíveis no escuro.** `Card.tsx:48` usa
  `shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)]` — preto semi-transparente sobre fundo já escuro não
  produz a mesma pista visual de elevação que produz sobre branco. Não é uma falha de WCAG (sombra
  não é o canal que carrega contraste de texto/gráfico obrigatório) — é uma perda estética aceita
  conscientemente; a elevação continua comunicada pela diferença `surface`/`surface-subtle` +
  `border` (Decisão 4). Registrado como item a olhar na Fase 4, não bloqueante.
- Fase 0 tem raio de alcance amplo (7+ componentes compartilhados) para uma mudança que, sozinha, não
  muda nada visível — risco de revisão "isso não faz nada" se o contexto de por que for perdido;
  mitigado por linkar este ADR no PR.
- `mplacas:theme` é mais uma chave de preferência de UI em `localStorage`, mais uma linha na
  allowlist de `tests/test_frontend_auth_contract.py` para manter.

## Validação

- Todos os pares da tabela da Decisão 4/5 passam no teste estendido de `contrastRatio.test.ts`
  (Fase 1) — `text-primary`/`text-secondary`/os três `-text` de severidade/`chart-reference`/
  `data-secondary`/`brand-primary`/`gray-400` a `gray-900`, todos ≥ 4.5:1 (texto) contra
  `--color-surface` e `--color-surface-subtle` escuros; ratios de preenchimento (`success`/
  `warning`/`danger`/`chart-track` como elemento gráfico) ≥ 3:1.
- `colorContrast.test.tsx` com glob corrigido continua verde nos dois temas (a regra é por nome de
  classe, não por tema).
- `resolveInitialTheme()` testado nas três ramificações (Fase 2).
- `pytest tests/test_frontend_auth_contract.py` verde com `mplacas:theme` na allowlist.
- `npm run build` com o bloco `[data-theme="dark"]` presente em `dist/assets/*.css` (checagem manual
  de classe gerada, mesma disciplina que `frontend-design` já exige).
- Varredura manual de Fase 4 sem novo hex solto fora de `index.css`.

## Reversibilidade

Alta. Toda a mudança é aditiva em CSS (bloco `[data-theme="dark"]` a mais, nada removido do `:root`
claro) e o mecanismo de aplicação é uma função isolada (`resolveInitialTheme`) mais um atributo no
`<html>` — desligar dark mode por completo é remover a chamada em `main.tsx` e o controle de UI, sem
tocar em nenhum componente. Reverter só a Fase 0 (normalização `bg-white`→token) não compensa, porque
não tem efeito colateral a desfazer (mesmo valor de cor). O único ponto de reversão com custo real
seria se a Opção B do CSP (hash) chegasse a ser adotada depois — nesse caso reverter exige também
tirar o hash de `_headers`.

## Riscos e o que fica fora de escopo

- **`LoginPage.tsx` fica inteiramente fora deste ADR.** Já é uma página fixa escura, sem nenhum
  token do design system, e **já tem 4 de 7 testes falhando hoje** (achado desta sessão, não deste
  ADR) — as duas asserções de "usa token, não `bg-blue-*`", o `aria-pressed` do toggle de senha, e o
  `aria-describedby`/`aria-invalid` do erro do formulário. Recomendo fortemente que isso seja
  roteado ao `worker`/`accessibility-specialist` como item separado, urgente e não relacionado a
  dark mode — `npm run test` está vermelho em `main` neste exato momento, independente deste ADR.
- **PDF/CSV/XLSX de `reports/export` não são tematizados.** São documentos renderizados no backend
  (ADR-027/028), sempre em estilo "impresso"/claro, para impressão em preto e branco — o
  compromisso de acessibilidade da skill `frontend-design` (leitura em P&B) já pressupõe isso.
  Dark mode é uma preferência de tela, não do documento exportado; nenhuma mudança proposta aqui.
- **`GRID_HEX` (`lib/dashboard/visuals.ts:136`)** aparenta código morto (sem uso em JSX hoje) — não
  corrigido por este ADR; se for reativado no futuro, precisa do mesmo tratamento de token que
  `TARGET_TICK_COLOR`/`AXIS_COLOR` receberam na Fase 0.
- **Meta tags nativas de tema** (`<meta name="color-scheme" content="light dark">` para
  scrollbar/form controls nativos do navegador seguirem o tema, `<meta name="theme-color">` dinâmico
  para a cor da barra do navegador mobile) não são parte da decisão — polimento de baixo custo que
  pode entrar em qualquer fase de implementação sem precisar de nova decisão de arquitetura.
- **Depois de aceito**: `.claude/skills/design-system/SKILL.md:23` e a seção "Dark mode" de
  `.claude/skills/frontend-design/SKILL.md` passam a descrever um estado que não é mais real (dizem
  que dark mode não existe) — atualizá-las é um passo de acompanhamento barato, não código, a fazer
  quando o usuário aceitar este ADR, não antes.
