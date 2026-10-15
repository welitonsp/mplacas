# ADR-077 — Identidade visual 2026-10: verde e marinho, temas corrigidos e linguagem limpa

## Status

**Aceito — 2026-10-15.** Direção visual aprovada pelo dono do produto a partir do protótipo
"MPlacas — nova interface" (Visão geral em desktop/celular, claro/escuro). Esta é a etapa 1 de
cinco: fundação (tokens, tipografia, componentes-base). As etapas seguintes (moldura do sistema,
gráficos, módulos, conferência) dependem desta e não mudam as decisões abaixo.

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

## Validação

- `src/test/contrastRatio.test.ts`: contraste WCAG 2.2 por fórmula nos dois temas, agora
  incluindo `gray-950`, `on-brand` sobre marca, item de menu ativo e preenchimentos de energia.
- `src/test/designTokensMirror.test.ts` (novo): falha se `designTokens.ts` divergir de
  `index.css`.
- `playwright.matriz.config.ts` (novo): capturas em desktop 1440, notebook 1280, tablet 820,
  celular (Pixel 7) e 360 px, claro e escuro; inclui `overflow.spec.ts`. Chrome e Edge usam o
  mesmo motor (Chromium). Firefox e Safari/iPhone entram com `PW_TODOS_NAVEGADORES=1` onde
  esses navegadores estiverem instalados.

## Consequências

- O visual muda em todas as telas de uma vez; layout e conteúdo continuam os mesmos até as
  etapas 2–4.
- Nenhuma mudança em dados, cálculos, contratos de API, autenticação ou permissões.
- A landing pública (`PublicHomePage`) tem CSS próprio e fica fora desta etapa.
