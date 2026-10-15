# ADR-077 — Identidade visual 2026-10: verde e marinho, temas corrigidos e linguagem limpa

## Status

**Aceito — 2026-10-15.** Direção visual aprovada pelo dono do produto a partir do protótipo
"MPlacas — nova interface" (Visão geral em desktop/celular, claro/escuro). Entregue em cinco
etapas (PRs #184–#188): fundação, moldura do sistema, gráficos, módulos e conferência. As
decisões de cada etapa estão abaixo; as da etapa 1 valem para todas as outras.

## Contexto

Capturas reais do painel (`e2e/screenshots.spec.ts`, fixtures de demonstração, 1440 px,
1280 px e celular, nos dois temas) mostraram:

| Problema | Causa no código |
|---|---|
| Títulos invisíveis no tema escuro ("Visão Geral", "Produção e Saúde da Usina", passos do plano) | `text-gray-950` e `--color-text`/`--color-text-muted` usados sem existir no tema escuro |
| Cartões brancos dentro da tela escura; ícones do menu como quadrados cinza | `bg-white/80`, `bg-white/70`, `ring-black/5` fixos |
| Botão primário com contraste reprovado no escuro | `text-white` sobre `--color-brand-primary` claro |
| Azul genérico do Tailwind como cor de marca | `--color-brand-primary: #2563eb`, sem relação com o relatório PDF (verde/marinho) |
| 110 rótulos em CAIXA ALTA com tracking largo | `uppercase tracking-[0.18em]` como estilo de rótulo padrão |
| Gradientes decorativos e brilho em barras | `linear-gradient`/`radial-gradient` e `shadow-[inset…]` |
| Página de 360 px rolando de lado no Financeiro | `sr-only` aplicado direto em `<table>` (tabela ignora `width: 1px`) |

## Decisão

1. **Duas cores de marca com papel fixo**, as mesmas do PDF mensal
   (`src/mplacas/reports/export/theme.py`): verde `#009C77` = energia produzida/aproveitada;
   marinho `#00406E` = estrutura, referência e energia da rede. Laranja e vermelho só para
   atenção. No escuro, as duas cores são clareadas (`#2BC79B`, `#7AAEDB`) com o mesmo papel.
2. **Mesmos nomes de token, valores novos.** O app inteiro já consumia `--color-*`; trocar
   os valores muda tudo de uma vez sem reescrever componentes. Tokens novos:
   `--color-on-brand`, `--color-surface-sunken`, `--color-chart-grid`,
   `--color-energy-export`, `--shadow-card`, `--radius-card`, `--radius-control`, e
   `--color-gray-950` nos dois temas. `--color-text`/`--color-text-muted` passam a existir.
3. **Escala de cinza fria** afinada com a tinta `#0E1B2A`, redefinida nos dois temas.
4. **Utilitários semânticos** via `@theme inline` (`bg-card`, `bg-page`, `text-ink`,
   `text-muted`, `border-line`, `text-brand-ink`, `font-display`) para os componentes novos.
5. **Tipografia:** Space Grotesk em `h1`/`h2` e números de destaque; Manrope no corpo.
   Rótulos em sentence case, sem `uppercase` (Fluent 2 Typography).
6. **Sem decoração:** fora gradientes, brilho interno em barras e sombras pesadas. Cartão =
   superfície + borda de 1 px + sombra leve (`--shadow-card`), raio `1.25rem`.
7. **Cabeçalho de módulo sem cartão em volta** (`PageHeader`).
8. **`sr-only` no wrapper, nunca na `<table>`.**

## Decisões das etapas 2 a 5

### Etapa 2 — moldura do sistema
9. **Um único `<nav>` de módulos** que é barra fixa no rodapé no celular (ícone sobre rótulo,
   alvo de 56 px) e lista lateral a partir de `lg`. Sai o "roteiro executivo" (pergunta-chave,
   foco, entregável, rotina de leitura): texto fixo repetido em toda tela.
10. **Marca única**: o símbolo da landing/favicon + o nome "MPlacas" (grafia da landing).
11. **Cabeçalho sem a linha "Pergunta / Leitura / Saída"** (`PageHeader.insights` continua
    existindo, mas nenhum módulo o usa).

### Etapa 3 — gráficos
12. Coluna com largura máxima (56 px por ciclo, 44 px por dia); topo do eixo arredondado para
    cima (`niceAxisMax`) — só o eixo muda, nunca o dado.
13. Dado parcial = mesma cor clara + contorno tracejado, nunca laranja (laranja é atenção).
14. **Fluxo de energia em duas barras de composição** no lugar do Sankey, cujo nó "Rede"
    somava injetado + importado num número que não existe na fatura. Autoconsumo e consumo
    continuam marcados "(estimado)"; toda legenda traz valor e unidade.

### Etapa 4 — módulos
15. **Cada número aparece uma vez por tela.** Os "sinais" do painel de decisão da Visão Geral
    e as "evidências" do painel financeiro continuam no modelo (`buildExecutiveDecision`,
    `buildFinancialDecision`), mas não são redesenhados ao lado de cartões que já mostram os
    mesmos valores.
16. **Ordem de leitura da Visão Geral**: estado + fluxo → indicadores → produção dos últimos 7
    dias → decisão → diagnósticos. No Financeiro, indicadores antes da decisão.
17. **Selo de natureza em todo indicador da Visão Geral**: Medido (telemetria/fatura),
    "Medido · parcial" quando o ciclo tem dias ausentes/provisórios/incompletos, Calculado
    (derivado pelo motor), Estimado (inferência). Sem valor, o selo diz "Carregando" ou
    "Indisponível" — nunca "Medido" num travessão.
18. Painéis de diagnóstico/decisão com rótulo + texto, sem caixas dentro de caixas; cor de
    estado só no texto do valor.

### Etapa 5 — conferência e login
19. Login: formulário primeiro no DOM e no celular; proposta à esquerda só no desktop.
20. Sai a "Prévia do cockpit" do login (Saúde 92% / Performance 87% / Disponibilidade 98%):
    números inventados numa tela de produto que vive de dado medido.
21. Senha sem placeholder (sugeria formato); bordas de campo com `gray-500` (≥ 3:1).

### Exceção de contraste documentada
`--color-energy-export` fica abaixo de 3:1 contra a superfície. Aceito porque o segmento nunca é
o único portador da informação (legenda com rótulo e kWh + `aria-label`); o teste de contraste
registra a exceção.

## Validação

- `src/test/contrastRatio.test.ts`: contraste WCAG 2.2 por fórmula nos dois temas, agora
  incluindo `gray-950`, `on-brand` sobre marca, item de menu ativo e preenchimentos de energia.
- `src/test/designTokensMirror.test.ts` (novo): falha se `designTokens.ts` divergir de
  `index.css`.
- Revisão independente (`quality-gate-reviewer`) do diff completo: sem P0/P1; os P2/P3 de
  honestidade de dado apontados foram corrigidos antes do PR final.
- `playwright.matriz.config.ts` (novo): capturas em desktop 1440, notebook 1280, tablet 820,
  celular (Pixel 7) e 360 px, claro e escuro; inclui `overflow.spec.ts`. Chrome e Edge usam o
  mesmo motor (Chromium). Firefox e Safari/iPhone entram com `PW_TODOS_NAVEGADORES=1` onde
  esses navegadores estiverem instalados.

## Consequências

- O visual e a organização das quatro telas do painel e do login mudam; o conteúdo informativo
  é o mesmo, sem repetição.
- Nenhuma mudança em dados, cálculos, contratos de API, autenticação ou permissões.
- A landing pública (`PublicHomePage`) tem CSS próprio e fica fora desta etapa.
