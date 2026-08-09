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

Definidos em `frontend/src/index.css`, via Tailwind v4 `@theme`/custom properties:

```css
--color-brand-primary: #1a56db;       /* ação primária, links, foco */
--color-brand-primary-dark: #1e429f;  /* hover de primary */
--color-brand-primary-light: #ebf5ff; /* fundo sutil de destaque */
--color-surface: #ffffff;             /* cards */
--color-surface-subtle: #f9fafb;      /* fundo de página */
--color-border: #e5e7eb;
--color-text-primary: #111827;
--color-text-secondary: #6b7280;
--color-danger: #dc2626;              /* alerta, health_score baixo, anomalia */
--color-danger-light: #fef2f2;
--color-success: #16a34a;             /* dentro do esperado, saúde 100 */
--color-success-light: #f0fdf4;
```

Use essas variáveis (via classes Tailwind mapeadas ou `var(--color-*)`) em vez de cores
arbitrárias. Se uma tela nova precisar de uma cor que não existe aqui (ex: um terceiro
estado "warning" além de success/danger), adicione ao `:root` do `index.css` — não
solte um hex novo direto no componente.

## Padrão de componente já em uso (siga, não invente um novo)

`frontend/src/pages/dashboard/OverviewPage.tsx` (e os demais módulos do dashboard) já
estabelecem o padrão de "card de métrica":

```tsx
<div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
  <p className="mt-2 text-2xl font-semibold text-gray-900">{value}</p>
</div>
```

Card branco, borda sutil, sombra leve, label pequeno em maiúscula/cinza, valor grande
em destaque. Novas telas/componentes de métrica devem seguir esse mesmo esqueleto
visual, não introduzir um estilo de card diferente por tela.

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

- Fonte do sistema já configurada (`system-ui, -apple-system, ...`) — não troque por
  uma fonte customizada carregada via CDN sem necessidade real; isso adiciona
  requisição de rede e risco de FOUT/FOIT sem ganho proporcional de legibilidade para
  este produto.
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
