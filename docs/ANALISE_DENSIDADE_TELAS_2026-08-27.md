# Análise de densidade e repetição — telas do painel

**Data:** 2026-08-27 · **Origem:** achado V-6, aberto pela captura visual (PR #142), que tornou as
telas observáveis pela primeira vez.

Complementa `docs/COMPARATIVO_VISUAL_2026-08-27.md`. Aquele documento comparou o Mplacas com projetos
equivalentes do GitHub sem ver as telas, e concluiu que faltavam tipografia, interação em gráfico e
consistência de token. Com as telas capturadas e medidas, aparece um problema **maior que os três**,
que a leitura de código não alcançava.

## Correção da hipótese anterior

O relato original foi *"as telas parecem de um sistema ruim"*, e a hipótese natural era falta de
acabamento visual. **Com as telas à vista, essa hipótese está errada.**

O que a Visão Geral mostra: hierarquia clara, roteiro de leitura numerado, qualidade de dado
declarada em toda parte (*"Aguardando dados"*, *"2 dias avaliados"*, *"Estimativa para o ciclo"*,
*"nunca é o dado oficial"*), diagrama de fluxo de energia bem construído, cor com função semântica.
Isso é acima da média do nicho.

O defeito é outro: **as telas cansam, não feiam.** Densidade e repetição.

## Evidência 1 — comprimento

Medido das capturas em `frontend/e2e/capturas/`, dividindo a altura da página pela altura da
viewport:

| Tela | Desktop (900px) | Mobile (852px) |
|---|---|---|
| Visão Geral | 2,7 telas | **12,4 telas** |
| Produção | 3,4 telas | **15,0 telas** |
| Técnico | 2,7 telas | 12,4 telas |
| Financeiro | 2,1 telas | 8,3 telas |
| Página pública | 6,9 telas | **24,9 telas** |

Quinze telas de rolagem para ler um módulo no celular. Nenhum dos comparáveis do GitHub chega perto
disso — e o dono do produto consulta o painel majoritariamente no telefone.

## Evidência 2 — o mesmo fato repetido de 3 a 6 vezes

Contagem manual sobre a captura de **Produção**, uma única tela:

| Fato | Vezes | Onde |
|---|---|---|
| "2 dias abaixo do esperado" | **6** | Resumo · Diagnóstico (card) · Diagnóstico (texto) · Evidências · Histórico ("2 dias com dado") · alerta vermelho |
| "88,6% de desempenho" | **4** | Diagnóstico (card) · Evidências · Histórico ("desempenho médio") · Histórico diária (título) |
| "pior dia 29/07 · −13,6%" | **4** | Diagnóstico (card) · Diagnóstico (texto) · Evidências · Histórico diária |
| "40 kWh no último dia" | **4** | Resumo · Último dia vs. esperada · Histórico ("melhor dia") · rodapé do gráfico |
| "44 kWh/dia de baseline" | **3** | Resumo · Último dia vs. esperada · rodapé do gráfico |

O bloco **"Evidências usadas"** é o caso mais claro: ele reafirma, em prosa corrida, exatamente os
quatro cards imediatamente acima dele. Não acrescenta informação — só altura.

O parágrafo do **critério de alerta** (*"Gatilho usa esperado/PR quando disponível; sem baseline,
compara 7 dias contra a janela anterior…"*) aparece **duas vezes na tela de Produção** e **mais uma
vez na Visão Geral** — três ocorrências do mesmo texto explicativo em dois módulos.

## Evidência 3 — a coluna esquerda vazia

No desktop, a barra lateral termina por volta de 730 px e o conteúdo segue até 2.391 px na Visão
Geral. São aproximadamente **1.600 px de coluna vazia** enquanto o conteúdo se empilha numa faixa
central estreita. O layout paga o custo de duas colunas e usa uma.

## Por que isso aconteceu — e por que não é descuido

A causa é visível na estrutura: existem **três apresentações do mesmo dado**, cada uma boa
isoladamente, empilhadas em vez de escolhidas.

1. **Resumo operacional** — 4 cards de número puro.
2. **Diagnóstico** — o mesmo dado, agora com impacto, próxima ação e severidade.
3. **Histórico** — o mesmo dado outra vez, com série temporal.

Cada uma foi provavelmente construída em momento diferente, resolvendo uma necessidade real. O que
faltou foi a passada final que pergunta: *dado que a de baixo existe, a de cima ainda precisa
existir?*

Isso conecta ao achado **V-5**: **ninguém via a tela inteira**. Cada seção foi revisada no seu
próprio teste de componente, onde cabe na altura de uma tela e parece razoável. A soma nunca foi
olhada por ninguém — até agora.

## Aplicando a arquitetura de informação do projeto

A skill `information-architecture` define três camadas, e as telas atuais **misturam as três dentro
de cada módulo**:

| Camada | Pergunta | Onde deveria viver |
|---|---|---|
| 1. Executiva | "Minha usina está bem?" | Visão Geral |
| 2. Energética/financeira | "O que produzi e economizei?" | Produção, Financeiro |
| 3. Técnica | "Por que mudou?" | Técnico |

Na tela de Produção convivem: número executivo (resumo), diagnóstico com plano de ação, evidência
técnica (critério de alerta, gatilho, baseline sazonal) e série histórica. O módulo Técnico existe
justamente para a camada 3 — mas a camada 3 aparece em Produção também.

A skill também alerta contra **"parede de cards do mesmo peso"**. O "Resumo operacional" são quatro
cards visualmente idênticos: "última produção" (o número que importa) compete em igualdade com
"sequência de atenção" (um contador).

## Recomendações

Aplicando `premium-product-ux`, cada item declara se serve à **decisão** ou é só estética.

### R-1 · Remover o bloco "Evidências usadas" · alto impacto, risco baixo

Ele reafirma os quatro cards logo acima. **Decisão:** nenhuma — o usuário já leu os mesmos números
dois centímetros antes. Corte direto, sem substituto.

### R-2 · Um fato, um lugar · alto impacto, risco médio

Para cada um dos 5 fatos repetidos, escolher **uma** casa e remover as outras. Critério: fica onde a
ação acontece.

- "2 dias abaixo" → fica no Diagnóstico (é onde há plano de ação); sai do Resumo, das Evidências e do
  rótulo do histórico.
- "88,6%" → fica no Resumo (é o indicador de acompanhamento); sai do Diagnóstico e dos dois títulos.
- "pior dia" → fica no Diagnóstico; sai do resto.

**Decisão:** direta. Hoje o usuário lê o mesmo número quatro vezes e precisa confirmar mentalmente
que é o mesmo — trabalho cognitivo puro, sem retorno.

### R-3 · Explicação de critério em um lugar só · médio impacto, risco baixo

O parágrafo do gatilho de alerta aparece 3× em 2 módulos. Deveria ser um `<details>`/tooltip junto do
indicador que ele explica, aberto sob demanda. **Decisão:** sim — quem já entendeu o critério não
precisa relê-lo em toda tela.

### R-4 · Usar a segunda coluna no desktop · médio impacto, risco médio

Aproveitar os ~1.600 px vazios movendo o histórico e o gráfico para a coluna lateral, em vez de
empilhar. Reduz rolagem de desktop sem cortar conteúdo. **Estética e decisão:** menos rolagem é menos
esforço para chegar ao dado.

### R-5 · Colapsar a camada técnica dentro de Produção · médio impacto, risco médio

Critério de alerta, baseline sazonal e legenda de anomalia são camada 3. A skill permite colapsar o
que é *genuinamente secundário para a decisão imediata* — **mas proíbe esconder diagnóstico crítico**,
e o alerta *"2 dias seguidos abaixo do esperado"* não pode ir para trás de um clique.

### R-6 · Quebrar a paridade visual do "Resumo operacional" · baixo impacto, risco baixo

"Última produção" merece mais peso que "sequência de atenção". Hoje os quatro cards são idênticos.
**Decisão:** sim — hierarquia visual é como o olho encontra o que importa primeiro.

## Ordem sugerida

| # | Ação | Por quê nesta posição |
|---|---|---|
| 1 | R-1 (cortar "Evidências usadas") | Maior redução por menor risco; é remoção pura |
| 2 | R-3 (critério em um lugar) | Independente do resto, corta 3 ocorrências |
| 3 | R-2 (um fato, um lugar) | O trabalho principal; fazer **por módulo**, um PR cada |
| 4 | R-6 (hierarquia do resumo) | Barato, e melhora a leitura do que sobrou |
| 5 | R-4 (segunda coluna) | Layout, depois que o conteúdo estiver enxuto |
| 6 | R-5 (colapsar camada técnica) | Por último, com o cuidado do diagnóstico crítico |

**Medir antes e depois em cada passo.** A captura visual existe agora e a altura da página é o
indicador objetivo: se a Produção no mobile não cair de 15 telas, a mudança não funcionou.

## O que NÃO fazer

- **Não redesenhar do zero.** A estrutura de camadas e o roteiro de leitura estão certos. O problema
  é excesso, e excesso se resolve removendo.
- **Não cortar declaração de qualidade de dado** (*"2 dias avaliados"*, *"dados parciais"*,
  *"estimativa"*). Elas parecem ruído e são o oposto disso — `data-quality-ui` as exige, e são o que
  distingue este produto de um dashboard bonito e mentiroso.
- **Não esconder o alerta crítico** ao colapsar seção. Regra dura da skill, não preferência.
- **Não tratar isso como trabalho de estética.** Cada item acima reduz esforço de leitura; nenhum é
  enfeite.
