# MPlacas — revisão visual e evolução do produto

**Data:** 15/10/2026
**Escopo:** landing pública, login, shell autenticado e módulos Visão Geral, Produção, Financeiro e Técnico.
**Branch:** `feat/ui-ux-premium-2026-10-14`, baseado na `main` atual.
**Publicação:** não realizada.

## Resumo executivo

A aplicação já tem fundações fortes — marca própria, tipografia local, tokens, componentes reutilizáveis, carregamento modular, estados explícitos e testes de interação. Não é necessário reconstruir o produto do zero. A evolução de maior valor está em tornar essas fundações sistemáticas: contraste coerente nos dois temas, navegação móvel operável por teclado, formulário de login imediatamente alcançável, caminhos de conversão contextuais e layouts realmente estreitos sem overflow.

A revisão percorreu as seis rotas com capturas Playwright em desktop e mobile, incluindo viewport de **320 CSS px**, e usou fixtures de demonstração interceptadas para o painel. Não foram utilizadas credenciais, sessões privadas, APIs de produção ou dados reais de clientes. As capturas servem à avaliação de hierarquia, densidade, wrapping e responsividade; não substituem ensaios com leitores de tela ou aprovação visual de marca.

## Achados por rota e decisão

| Rota/superfície | Diagnóstico visual e estrutural | Evolução desta entrega | Próximo refinamento prioritário |
|---|---|---|---|
| `/` — landing | Direção editorial premium e narrativa comercial coerente. No celular, a página era excessivamente longa; rótulos e anotações funcionais eram pequenos/contrastavam pouco. Os três cards de capacidade apontavam ao mesmo destino. O menu não oferecia Escape, foco inicial nem atalho ao conteúdo. | Skip link; foco ao primeiro link ao abrir; Escape fecha e devolve foco; alvos do menu de 44–48 px; destinos específicos para os três cards; rótulos mais legíveis; redução de alturas e paddings mobile sem remover FAQ ou CTAs. | Revisar densidade de todas as seções a 320/375/390 px com critérios editoriais; acrescentar fallback visual para imagens e cobertura automatizada de foco/contraste renderizado. |
| `/login` — autenticação | A proposta visual vinha antes da tarefa e empurrava o formulário para baixo da dobra no celular. Marca duplicada, contorno de campo muito discreto, placeholder da senha sugeria formato e a aba herdava o título público. | Formulário primeiro em telas estreitas e preservação do layout de duas colunas em desktop; marca vetorial única no cartão de acesso; bordas mais perceptíveis; remoção do placeholder prescritivo; título da aba específico de login. | Reavaliar ordem semântica das headings para que a hierarquia de leitura coincida totalmente com a nova ordem visual. |
| `/dashboard/visao-geral` — Visão Geral | Boa moldura de decisão e números com unidades/contexto; a primeira leitura pode repetir sinais entre hero, decisão e KPIs. O SVG Sankey reduz escala em telas estreitas. | Corrigidos tokens que afetavam títulos do shell e referências semânticas de texto; tabela equivalente do gráfico mantida acessível sem alargar o documento. Nenhuma métrica ou cálculo foi alterado. | Reduzir repetição entre superfícies executivas; garantir identidade do módulo em loading/erro/vazio e expor alternativa semântica para o mini-gráfico diário. |
| `/dashboard/producao` — Produção | Há bastante evidência operacional e segmentos extensos; séries horizontais exigem descoberta de conteúdo lateral e alguns cartões de comparação ficam estreitos em larguras intermediárias. | Proteção de overflow no widget de séries e sincronização do E2E de navegação por heading; tokens visuais sistêmicos corrigidos. | Desacoplar a renderização do histórico do dado esperado, consolidar erros/retries e equilibrar a grade de comparação em tablets. |
| `/dashboard/financeiro` — Financeiro | Decisão, resumo e detalhes repetem alguns indicadores; campos de custo, energia e retorno têm hierarquia/ritmo diferentes. Uma tabela semântica de gráfico, invisível visualmente, podia alargar o viewport. | O viewport de 320 px foi verificado com o conteúdo completo do módulo; tabelas acessíveis usam layout fixo e posicionamento fora da área visível para manter dados disponíveis a leitores de tela sem alargar a página. Tokens semânticos ausentes para títulos e texto muted foram definidos. | Manter decisão no topo, reduzir repetição entre resumo e detalhes e dar shell contextual aos estados de retorno/erro. |
| `/dashboard/tecnico` — Técnico | Há muita evidência em sequência longa; labels de perdas truncados podem dificultar leitura por toque e em telas pequenas. | Tokens de texto escuro agora cobrem a escala até gray-950 e os aliases semânticos; estrutura e dados técnicos foram preservados. | Adicionar índice/âncoras para inversores e desempenho, permitir quebra de labels sem depender de tooltip e distinguir claramente erro de falta de dados. |
| Shell `/dashboard/*` | Tema escuro oferecido pelo produto não tinha contraparte para gray-950; existiam usos de `--color-text` e `--color-text-muted` sem definição. O avatar declarava `role=menu` embora contivesse apenas uma ação e não implementasse navegação composta por setas. | Tokens adicionados para claro/escuro e contrato coberto por teste WCAG; marca duplicada removida do cabeçalho; ação de saída virou disclosure simples com botão nativo; Escape restaura o foco. | Manter shell, h1, foco e ação em todos os estados assíncronos e criar skeletons coerentes com cada módulo. |

## Mudanças implementadas

1. **Tokens e legibilidade:** `--color-text`, `--color-text-muted` e gray-950 declarados nas contrapartes de tema; os valores espelhados no cálculo de contraste e testados sobre superfícies clara e escura.
2. **Navegação e acessibilidade:** skip link na landing; menu mobile da landing com foco, Escape e retorno ao toggle; alvos maiores; disclosure do operador com semântica simples e Escape com restauração de foco.
3. **Conversão:** links dos cards de capacidade agora conduzem a seções pertinentes; o formulário de login precede o conteúdo promocional no mobile.
4. **Acabamento do login:** marca sem duplicação, bordas de campo mais claras, placeholder de senha removido e título específico da rota.
5. **Reflow:** tabelas `sr-only` dos dois gráficos usam layout fixo e ficam fora da área visível para não empurrar o documento pela largura intrínseca do conteúdo; o E2E espera o heading da rota antes de medir a página.
6. **Landing mobile:** cartões de capacidade e blocos editoriais menos altos, sem retirar informação, FAQ ou CTAs.

**Invariantes:** nenhuma mudança no backend, contratos, autenticação, permissões, valores, datas, unidades, cálculos energéticos/financeiros ou severidades.

## Validação

- TypeScript: `npm run type-check` — aprovado.
- Testes unitários: `npm test` — **89 arquivos, 1.015 testes aprovados** na execução completa definitiva.
- Playwright de capturas: landing, login e quatro módulos em desktop, mobile e 320 px.
- E2E de overflow: **passou em todos os módulos a 320 CSS px** na execução final. A primeira rodada identificou tabelas semânticas ocultas causando largura intrínseca extra; as tabelas foram corrigidas e o módulo/rota agora é aguardado pelo heading antes da medição.
- Build de produção: aprovado.
- Orçamento de bundle: aprovado em todos os chunks; landing combinada JS+CSS ficou dentro do teto de 15 kB gzip.
- Higiene Git: `git diff --check` sem erros.

## Backlog recomendado para a próxima etapa

A evolução entregue corrige um conjunto transversal de alto impacto, mas não declara todas as observações de UX como resolvidas. Os próximos itens com maior retorno são:

1. **Estados assíncronos:** manter título, contexto e ação em loading, erro e vazio; criar skeletons por módulo.
2. **Visualizações:** alternativa textual do mini-gráfico da Visão Geral; affordance de rolagem nas séries; labels completos no diagnóstico Técnico.
3. **Produção e retry:** liberar o histórico quando dados independentes já chegaram e apresentar um único erro/retry por recurso.
4. **Hierarquia de painel:** reduzir repetição entre decisão, resumo e evidência sem suprimir dados ou unidades.
5. **Revisão com tecnologia assistiva:** ensaio manual com leitor de tela e teclado completo, além de screenshots de tema claro/escuro em estados de sucesso, loading, erro e vazio.

## Referências de projeto

- W3C — [WCAG 2.2](https://www.w3.org/TR/WCAG22/) e [Reflow (1.4.10)](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).
- Microsoft — [Fluent 2 Typography](https://fluent2.microsoft.design/typography).
- Google — [Material Design 3 Typography](https://m3.material.io/styles/typography) e [Spacing](https://m3.material.io/styles/spacing).
- Referências reunidas em `docs/REFERENCIAS_UI_DESIGN_2026-10-14.md`.
