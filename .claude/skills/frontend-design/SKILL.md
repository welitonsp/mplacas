---
name: frontend-design
description: Use SEMPRE que for criar, refatorar ou dar polimento visual a qualquer tela do frontend do Mplacas (src/frontend, React 19 + Tailwind CSS v4) — dashboard, login, cards de métrica, tabelas de fatura, gráficos. Garante consistência com a paleta/tipografia já estabelecidas no projeto e prioriza legibilidade de dado financeiro/energético sobre efeito visual. Para gráficos e visualizações de dado especificamente, combine com a skill dataviz do sistema.
---

# Design do frontend — Mplacas

## Contexto do produto (por que isso não é um dashboard de consumo)

O Mplacas mostra dado financeiro e de geração de energia para o dono de uma usina solar
tomar decisão real (ex: "minha usina está gerando o esperado?", "quanto economizei?").
**Clareza e confiança no número importam mais que efeito visual.** Modelos de referência
corretos são Stripe, Vercel e Linear — mas pelo que esses produtos realmente fazem
(hierarquia tipográfica limpa, cor usada com moderação para guiar atenção, muito
espaço em branco), não pela caricatura de "glassmorphism"/gradiente pesado que às
vezes se associa a "premium". Um gradiente vistoso atrás de um número de kWh dificulta
ler o número — é o oposto do objetivo.

## Paleta e tokens já estabelecidos (não invente uma paleta nova)

A identidade vigente é a da **ADR-077 (2026-10)** — leia `docs/ADR-077-identidade-visual-2026-10.md`
antes de mexer em visual. Resumo do que ela fixou:

- **Duas cores de marca com papel fixo**, as mesmas do PDF mensal: **verde `#009C77`** =
  energia produzida/aproveitada; **marinho `#00406E`** = estrutura, referência, ação primária
  e energia da rede. No escuro: `#2BC79B` e `#7AAEDB`, mesmo papel. Laranja e vermelho só
  para atenção — nunca decoração.
- Valores em `frontend/src/index.css` (`:root` e `:root[data-theme="dark"]`), espelhados em
  `frontend/src/test/designTokens.ts` (o teste `designTokensMirror` falha se divergirem; o
  `contrastRatio` calcula WCAG nos dois temas). **Não copie hex desta skill** — leia o
  `index.css`, que é a fonte de verdade.
- Prefira os utilitários semânticos do `@theme inline`: `bg-page`, `bg-card`, `bg-sunken`,
  `border-line`, `text-ink`, `text-muted`, `bg-brand`, `text-brand-ink` (texto sobre marca),
  `font-display`. Nunca `bg-white`, `text-white`, `text-gray-950` ou `ring-black/5` fixos —
  foi isso que quebrou o tema escuro antes da ADR-077.
- Cor nova só como token no `index.css` (+ espelho em `designTokens.ts`), nunca hex solto
  no componente. Severidade: use as variantes `-text` (`--color-success-text` etc.) para
  texto; os preenchimentos não passam 4,5:1 como texto no tema claro.

## Padrão de componente já em uso (siga, não invente um novo)

Cartão = `Card` (`frontend/src/components/Card.tsx`): superfície `--color-surface`, borda de
1 px `--color-border`, sombra leve `--shadow-card`, raio `--radius-card` (1,25rem). Métrica
simples = `SummaryTile`: rótulo em **sentence case** (13 px, `text-muted`), valor grande em
destaque, selo de natureza (Medido / Medido · parcial / Calculado / Estimado).

Regras da ADR-077 que valem para todo componente novo:
- **Sem `uppercase` com tracking largo** em rótulo — sentence case.
- **Sem decoração:** nada de `linear-gradient`/`radial-gradient`, brilho interno em barra,
  sombra pesada ou borrão decorativo.
- **Cor de estado só no texto/ícone do valor** — sem faixa lateral colorida (`border-l-4`),
  sem caixa dentro de caixa.
- **Cada número aparece uma vez por tela.**
- Cabeçalho de módulo é o `PageHeader`, sem cartão em volta. `sr-only` vai no wrapper,
  nunca direto na `<table>`.

## Prioridades nesta ordem (nunca inverta)

1. **O número certo, legível, sem ambiguidade.** Unidade sempre visível (kWh, R$, %).
   Nunca deixe o usuário adivinhar se um valor é kWh ou R$.
2. **Estado do dado explícito.** O projeto já modela qualidade de dado
   (`missing_days`, `provisional_days`, `incomplete_days`, `unavailable_days` — ver
   `energy/executive/latest`) — a UI precisa expor isso, não esconder atrás de um
   número "bonito" que pode estar incompleto. Um card com dado provisório deve
   parecer visualmente diferente de um com dado consolidado (ex: borda tracejada,
   badge "provisório"), não idêntico.
3. **Hierarquia visual por severidade**, usando os tokens `success`/`danger` já
   existentes: `health_score` alto = verde, anomalia/health baixo = vermelho,
   neutro = texto secundário cinza. Não decore estado com cor fora dessa lógica.
4. **Só depois disso, polimento** (espaçamento, sombra, animação leve de transição).

## Tipografia e espaçamento

- Fontes self-hosted em `frontend/public/fonts/` (sem CDN): **Space Grotesk** em `h1`/`h2`
  e números de destaque (`font-display`), **Manrope** no corpo. Não adicione fonte nova
  sem ADR.
- Texto do painel com no mínimo 12 px; prefira os tamanhos já usados (12/13/15/16/18 e
  28/34 para números) em vez de criar `text-[Npx]` novo.
- Espaçamento generoso entre cards (`gap-4`/`gap-6` do grid já usado), mas sem exagerar
  a ponto de exigir scroll para ver 2 números relacionados (ex: produção e produção
  esperada devem estar visualmente próximos, são comparados pelo usuário).

## Acessibilidade — não opcional

- Contraste mínimo AA (não AAA à custa de legibilidade, AA já é obrigatório).
- Todo ícone/cor que carrega significado (verde=ok, vermelho=alerta) precisa de um
  rótulo textual também — não confie só na cor (usuário com daltonismo, ou export para
  PDF em preto e branco, que este projeto já faz via `reports/export`).
- Elementos interativos (botões, links) precisam de estado de foco visível — não remova
  o outline do navegador sem substituir por um equivalente visível.

## Dark mode

Dark mode foi implementado (ADR-071). Componentes precisam respeitar tanto a paleta clara
quanto a escura (ver `:root[data-theme="dark"]` em `index.css`). Ao refatorar ou adicionar
componentes, garanta que o contraste e a legibilidade se mantêm em ambos os temas.

## Para gráficos e visualizações de dado

Combine esta skill com a skill `dataviz` do sistema sempre que for desenhar um gráfico,
sparkline, heatmap ou qualquer visualização — ela já resolve paleta categórica/
sequencial validada e as regras de forma/interação. Não reinvente isso aqui.

## Build (não pule esta checagem)

Depois de qualquer mudança de classe Tailwind nova, rode `npm run build` em
`frontend/` e confirme que a classe realmente aparece no CSS gerado
(`grep` no arquivo em `dist/assets/*.css`) antes de considerar a tarefa concluída — o
projeto já teve um bug real de classes sendo escritas no `.tsx` mas nunca geradas no
CSS final por falta do plugin `@tailwindcss/vite` no `vite.config.ts` (corrigido em
`b186f67`). Não repita esse erro assumindo que "a classe está no JSX" é suficiente.
