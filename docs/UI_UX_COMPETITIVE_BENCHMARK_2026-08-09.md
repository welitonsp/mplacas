# Benchmark competitivo de UI/UX 2026 — Mplacas

**Data:** 2026-08-09  
**Escopo:** plataformas de monitoramento e gestão de energia associadas aos dez maiores fabricantes de inversores residenciais importados pelo Brasil no 1º semestre de 2025.  
**Objetivo:** orientar o redesign do frontend do Mplacas, preservando rigor técnico e elevando clareza, percepção de qualidade e utilidade operacional.

---

## 1. Conclusão executiva

O Mplacas já possui uma base de engenharia acima da aparência que entrega: rotas por módulo, estados de erro e ausência honestos, tema claro/escuro, acessibilidade testada, responsividade e gráficos próprios. O problema central não é falta de componentes. É a falta de uma narrativa visual simples, memorável e orientada às três perguntas que o usuário faz primeiro:

1. **Minha usina está bem?**
2. **Quanto ela produziu e para onde foi a energia?**
3. **Quanto economizei e o que exige ação?**

Os melhores produtos estudados não vencem por mostrar mais métricas. Eles vencem porque priorizam o “agora”, tornam o fluxo de energia o centro da experiência, permitem alternar períodos sem esforço e separam a visão do proprietário da visão de operação e manutenção.

Para o Mplacas chegar a uma experiência percebida como 10/10, a recomendação é:

- transformar a Visão Geral em um **cockpit de uma tela**, não uma coleção de cards;
- dar destaque imediato a **estado, último dado, produção, economia e atenção necessária**;
- usar o **fluxo de energia como narrativa visual**, com menos caixas aninhadas;
- reduzir bordas, títulos repetidos e superfícies concorrentes;
- criar uma identidade visual solar própria, sem perder o azul de confiança;
- evoluir Produção, Financeiro e Técnico como espaços especializados;
- adicionar Central de Alertas e Relatórios, hoje lacunas claras de produto;
- preservar como diferencial tudo que comunica qualidade, cobertura, parcialidade e origem do dado.

---

## 2. Como o Top 10 foi definido

Não existe um ranking público e auditado de usuários ativos de plataformas solares no Brasil. Para não criar uma lista arbitrária, foi usado como proxy o ranking de volume importado de inversores residenciais de até 9,9 kW no 1º semestre de 2025, publicado pela Greener.

Os dez fabricantes concentraram **78% do volume total importado** nessa faixa. A ordem publicada foi:

1. Huawei — 381 MW
2. SAJ — 245 MW
3. Solis — 239 MW
4. Deye — 170 MW
5. Sungrow — 122 MW
6. GoodWe — 120 MW
7. SOFAR — 119 MW
8. FoxESS — 107 MW
9. Hoymiles — 105 MW
10. Growatt — 104 MW

Fonte-base: [Estudo Estratégico de Geração Distribuída — Greener, páginas 25–26](https://canalsolar.com.br/wp-content/uploads/2025/09/link.pdf).

### Limitações

- O ranking mede volume de equipamentos, não usuários da plataforma.
- Recursos podem variar por modelo de inversor, medidor, bateria, perfil de acesso e região.
- Portais autenticados não foram acessados. A análise usa páginas oficiais, manuais e imagens públicas.
- Detalhes puramente visuais foram tratados como evidência parcial quando só havia material promocional.
- “10/10” não é uma nota possível de validar apenas por código: exige protótipo renderizado, testes de usabilidade e métricas reais.

---

## 3. Os dez sistemas e o que ensinam

### 3.1 Huawei FusionSolar

**Padrão de produto:** ecossistema unificado para solar, consumo, bateria, rede, carregador e dispositivos da casa.

**O que a interface prioriza:**

- fluxo de energia em tempo real como visual principal;
- visão residencial simples e camada profissional de O&M;
- alarmes com prioridade;
- mapa físico/lógico e monitoramento em nível de módulo quando o hardware permite;
- dashboard de KPIs, relatórios, dispositivos e gestão de alarmes;
- experiência integrada entre app e web.

**Força:** comunica um sistema complexo como uma história visual de energia circulando entre fontes e destinos.

**Risco a não copiar:** “tempo real” só funciona quando o dado realmente é atualizado nessa cadência. O Mplacas deve continuar carimbando ciclo e data do último dado em vez de simular instantaneidade.

**Lição para o Mplacas:** o fluxo precisa ser o centro da Visão Geral, mas com a honestidade temporal já existente no produto.

Fontes: [FusionSolar Smart Home Energy Management](https://solar.huawei.com/en/products/smart-pv-management-system/), [FusionSolar Smart PV Plant Management](https://solar.huawei.com/en/products/smart-pv-plant-management-system/), [datasheet do FusionSolar](https://solar.huawei.com/-/media/Solar/attachment/pdf/th/datasheet/FusionSolar_Smart_PV_ManagSyst.pdf).

### 3.2 SAJ elekeeper

**Padrão de produto:** hub de energia residencial e comercial com monitoramento, controle e automação assistida por IA.

**O que a interface prioriza:**

- fluxo de produção, armazenamento, consumo e venda;
- diagnóstico completo acionado em um passo;
- visualização por módulo;
- estratégias de tarifa e agendamento;
- modos de operação, bateria e proteção contra falta de energia;
- ROI, ganhos e benefícios ambientais;
- mesma linguagem visual em web, tablet e mobile.

**Força:** apresenta inteligência e controle como ações concretas, não apenas relatórios.

**Risco a não copiar:** a própria SAJ descreve o visual como neomórfico. Esse estilo pode reduzir contraste, confundir affordances e envelhecer rapidamente se usado em excesso.

**Lição para o Mplacas:** diagnósticos devem terminar em uma ação clara. “Detectamos” é menos útil que “detectamos, este é o impacto, faça isto agora”.

Fontes: [SAJ elekeeper](https://www.saj-electric.com/elekeeper), [manual do elekeeper](https://www.saj-electric.com/hubfs/Product%20Url/elekeeper/elekeeper%20App%20User%20Manual%20V3-EN.pdf).

### 3.3 SolisCloud

**Padrão de produto:** monitoramento e manutenção para proprietário, instalador e organização.

**O que a interface prioriza:**

- fluxo de energia ao vivo para sistemas solares e armazenamento;
- alarmes configuráveis com recomendações;
- saúde do sistema e localização de falhas;
- análise e varredura de curva I-V;
- gestão multiusina e multiequipe;
- rendimento, ganhos, CO₂ e árvores equivalentes;
- papéis separados para proprietário e organização.

**Força:** boa ponte entre visão executiva e O&M profundo.

**Risco a não copiar:** misturar indicadores ambientais, financeiros, técnicos e operacionais na mesma tela aumenta a densidade e reduz a prioridade visual.

**Lição para o Mplacas:** manter as quatro rotas atuais é correto; o resumo deve mostrar o essencial e oferecer aprofundamento, não tentar ser o portal inteiro.

Fontes: [SolisCloud](https://www.solisinverters.com/br/SolisCloud/SolisCloud_br), [visão geral oficial](https://solis-service.solisinverters.com/en/support/solutions/articles/44002492965-soliscloud-monitoring-platform-overview), [manual do SolisCloud](https://soliscloud.com/SolisCloud%20Operation%20Manual-UserV1.0.pdf).

### 3.4 Deye com SOLARMAN Smart / Business

**Padrão de produto:** aplicativo para proprietário e painel operacional para integradores, usados por diversos fabricantes e soluções white-label.

**O que a interface prioriza:**

- potência, produção, consumo, importação/exportação e fluxo;
- histórico por data e condição;
- informações de receita e configuração da residência;
- página de dispositivo com parâmetros e gráficos;
- no Business: estados de usina clicáveis, offline parcial/total, alertas, rankings e visão consolidada da carteira.

**Força:** a visão de carteira transforma KPIs em filtros operacionais. Clicar em “5 usinas offline” leva diretamente ao conjunto que exige atenção.

**Risco a não copiar:** interfaces white-label tendem a acumular opções e terminologia técnica, sacrificando personalidade e clareza para o proprietário.

**Lição para o Mplacas:** cada KPI de atenção deve ser navegável e levar ao problema filtrado; badges puramente informativos desperdiçam a intenção do usuário.

Fontes: [Deye — manual que referencia SOLARMAN Smart e Business](https://www.deyeinverter.com/deyeinverter/2023/09/21/%E3%80%90b%E3%80%9130240301002101-%E5%BE%AE%E9%80%86%E8%AF%B4%E6%98%8E%E4%B9%A6-sun-m60-100g3-eu-q0-eu-230-%E5%BE%B7%E4%B8%9A%E8%8B%B1%E6%96%87.pdf), [SOLARMAN Smart — Data View](https://helpcenter.solarmanpv.com/portal/en/kb/articles/data-view), [SOLARMAN Business — Dashboard](https://helpcenter.solarmanpv.com/portal/en/kb/articles/dashboard).

### 3.5 Sungrow iSolarCloud

**Padrão de produto:** plataforma de monitoramento remoto e O&M com profundidade de usina, equipamento e processo operacional.

**O que a interface prioriza:**

- produção do dia, acumulado, receita, CO₂, tendência e rankings;
- alternância por dia, mês e ano;
- mapa e lista de usinas;
- gráficos configuráveis por planta, inversor, medidor e estação meteorológica;
- alarmes com confirmação, responsável, ordem de serviço e encerramento;
- relatórios diários, mensais, anuais e personalizados;
- análise de curvas, strings e dispositivos.

**Força:** é o benchmark mais forte do grupo para processo de O&M e rastreabilidade de uma ocorrência até o fechamento.

**Risco a não copiar:** a camada profissional é densa e inadequada como tela inicial de proprietário.

**Lição para o Mplacas:** a futura Central de Alertas deve ter estado, responsável, histórico e resolução; uma lista de mensagens não é suficiente.

Fonte: [manual oficial do iSolarCloud](https://img.isolarcloud.com/pdf/UserManual/iSolarCloud%20User%20Manual_en.pdf).

### 3.6 GoodWe SEMS+ / SEMS Portal

**Padrão de produto:** gestão unificada de energia para proprietário e instalador, com nova geração lançada em 2026.

**O que a interface prioriza:**

- linguagem visual atualizada e coerente entre web e app;
- contexto do mundo real, como clima e cenário de uso;
- tema claro e escuro;
- fluxo de energia, Sankey e mapas de calor;
- atualização de indicadores principais em dez segundos;
- comparação entre usinas e entre dispositivos;
- centro do proprietário diferente do centro do instalador;
- análise de curva I-V e consistência de bateria.

**Força:** é a referência mais próxima do que o Mplacas deve buscar em arquitetura visual: mesma base de design, mas diferentes níveis de complexidade por perfil.

**Risco a não copiar:** IA, clima, tarifas e dispositivos conectados só devem aparecer quando houver dado confiável e ação real. Elementos “smart” decorativos diminuem confiança.

**Lição para o Mplacas:** construir uma gramática visual de dados que funcione em todas as rotas; não desenhar cada página como produto separado.

Fontes: [GoodWe — lançamento do SEMS+](https://es.goodwe.com/next-generation-smart-energy-management-app-from-goodwe), [manual do SEMS Portal](https://cz.goodwe.com/Ftp/EN/Downloads/User%20Manual/GW_SEMS%20Portal-User%20Manual-EN.pdf), [manual do aplicativo SEMS Portal](https://en.goodwe.com/Ftp/EN/Downloads/User%20Manual/GW_SEMS%20Portal%20APP_User%20Manual-EN.pdf).

### 3.7 SOFAR Cloud

**Padrão de produto:** gestão do ciclo de vida de usinas fotovoltaicas e armazenamento para proprietário, instalador e O&M.

**O que a interface prioriza:**

- operação da usina em tempo real;
- gestão em lote de equipamentos;
- controle e atualização remotos;
- alarmes em nível de minuto;
- dados atuais e históricos por dispositivo;
- estatísticas de rendimento e receita;
- versões web e app com experiências por perfil.

**Força:** boa cobertura funcional do ciclo operacional completo.

**Risco a não copiar:** interfaces orientadas a equipamentos podem fazer a unidade consumidora desaparecer atrás de números de série e parâmetros.

**Lição para o Mplacas:** a usina, o ciclo de faturamento e o impacto para o cliente devem continuar sendo a unidade principal; o dispositivo é detalhe técnico.

Fontes: [SOFAR Cloud](https://www.sofarsolar.com/cloud.html), [manual do SofarCloud](https://www.sofarsolar.com/upload/file/20251104/1762243911541013797.pdf).

### 3.8 FoxCloud 2.0

**Padrão de produto:** gestão residencial orientada a energia, tarifas e receita, acompanhada por um painel profissional de carteira.

**O que a interface prioriza:**

- tendências por dia, semana, mês e ano;
- produção e consumo com insights acionáveis;
- receita total, crescimento diário e decomposição de fontes;
- tarifas dinâmicas e configuração por faixas;
- assistente e otimização por IA;
- painel BI com ranking, estatísticas, tendências e GIS para instaladores;
- gamificação ambiental com “floresta” digital.

**Força:** demonstra que financeiro pode ser visual, explicável e parte central da experiência, não uma tabela secundária.

**Risco a não copiar:** gamificação ambiental e IA podem banalizar um produto cujo diferencial é auditabilidade.

**Lição para o Mplacas:** economia e retorno precisam ganhar narrativa visual própria, incluindo composição, variação e premissas, sem transformar o dado em marketing.

Fonte: [FoxCloud 2.0](https://www.fox-ess.com/products/foxcloud).

### 3.9 Hoymiles S-Miles Cloud

**Padrão de produto:** monitoramento de microinversores com visibilidade até módulo, mais portal profissional para carteira.

**O que a interface prioriza:**

- produção e consumo em tempo real;
- layout físico dos módulos com edição por arrastar e soltar;
- tensão, corrente, potência e temperatura por painel;
- gestão de plantas, dispositivos, firmware e atualizações;
- relatórios personalizados;
- alarmes e solução remota de problemas;
- visão consolidada para múltiplas plantas.

**Força:** a topologia física dá contexto imediato ao problema e reduz o tempo entre alerta e localização.

**Risco a não copiar:** para sistemas sem telemetria por módulo, um mapa visual detalhado pode prometer precisão que o dado não suporta.

**Lição para o Mplacas:** visualizações devem refletir a granularidade real. Quando não existe dado por painel, comunicar a limitação é melhor que desenhar um “mapa” fictício.

Fontes: [S-Miles Cloud](https://www.hoymiles.com/smiles-cloud.html), [S-Miles para profissionais](https://www.hoymiles.com/us/professional/), [manual do S-Miles Cloud](https://static.hoymiles.com/cfs/doc/S-miles%20Cloud%20User%20Guide%20V.06.pdf).

### 3.10 Growatt ShinePhone / ShineServer / OSS

**Padrão de produto:** ecossistema dividido entre aplicativo do proprietário, portal web, ferramenta leve de manutenção e plataforma O&M.

**O que a interface prioriza:**

- monitoramento simples para o proprietário;
- tendência de energia e autoconsumo no portal web;
- histórico, relatórios, alarmes e notificações;
- comissionamento e firmware em ferramentas próprias;
- curva I-V e manutenção inteligente no OSS profissional.

**Força:** separa tarefas simples do proprietário das tarefas profundas do instalador.

**Risco a não copiar:** a fragmentação entre ShinePhone, ShineServer, ShineTools e OSS cria custo cognitivo e sensação de ecossistema quebrado.

**Lição para o Mplacas:** as quatro rotas devem parecer partes de um único produto. Não criar aplicativos, shells ou linguagens visuais diferentes por função.

Fontes: [Growatt — plataforma de monitoramento no Brasil](https://br.growatt.com/products/plataforma-de-monitoramento-growatt), [manual que descreve o ShinePhone](https://us.growatt.com/upload/file/MIN_3-11.4kTL-XH-US_Commissioning_Guide_EN_202501.pdf).

---

## 4. Matriz de padrões do mercado

Legenda: **●** = evidenciado nas fontes públicas; **◐** = parcial, depende de hardware/perfil ou aparece em uma camada do ecossistema; **—** = não foi confirmado nas fontes usadas.

| Plataforma | Fluxo de energia | Período flexível | Alertas/O&M | Financeiro/receita | Multiusina | Módulo/dispositivo | Padrão mais valioso |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| Huawei FusionSolar | ● | ● | ● | ◐ | ● | ● | energia como narrativa visual |
| SAJ elekeeper | ● | ● | ● | ● | ◐ | ● | diagnóstico e ação em um passo |
| SolisCloud | ● | ● | ● | ● | ● | ● | ponte entre dono e O&M |
| Deye / SOLARMAN | ● | ● | ● | ● | ● | ● | KPIs operacionais clicáveis |
| Sungrow iSolarCloud | ◐ | ● | ● | ● | ● | ● | ciclo completo do alerta |
| GoodWe SEMS+ | ● | ● | ● | ● | ● | ● | linguagem única, perfis distintos |
| SOFAR Cloud | ● | ● | ● | ● | ● | ● | gestão de ciclo de vida |
| FoxCloud 2.0 | ● | ● | ● | ● | ● | ◐ | narrativa financeira e BI |
| Hoymiles S-Miles | ● | ● | ● | ◐ | ● | ● | topologia física do sistema |
| Growatt Shine | ◐ | ● | ● | ◐ | ● | ● | separação por tarefa/perfil |

### Padrões praticamente universais

1. O primeiro quadro responde ao **estado atual**.
2. Fluxo de energia é mais compreensível que cinco cards independentes.
3. Dia, mês, ano e total são controles de primeira classe.
4. Alertas possuem histórico, severidade e estado.
5. Proprietário e instalador não recebem a mesma densidade.
6. Multiusina exige mapa/lista, filtros e ranking por atenção.
7. Receita, economia e benefício são apresentados com contexto temporal.
8. O dado técnico aparece sob demanda, não domina a tela inicial residencial.

---

## 5. Auditoria do Mplacas atual

### 5.1 O que o código já faz bem

O frontend atual avançou significativamente em relação à auditoria de 2026-08-04:

- shell único com cabeçalho fixo, seletor de usina e preferência de tema;
- quatro rotas coerentes: Visão Geral, Produção, Financeiro e Técnico;
- tema claro/escuro com tokens e testes de contraste;
- navegação, foco visível, skip link e alternativas tabulares para gráficos;
- fluxo de energia com período explícito;
- saúde da usina, severidade, frescor do dado e resumo de atenção;
- períodos e lacunas de produção tratados sem fabricar zero;
- ROI/payback e cadastro de investimento;
- visualizações próprias: Gauge, Sankey, colunas, barras empilhadas, bullet e sparkline;
- multiusina no contexto do frontend;
- estados de erro, carregamento, ausência e dados parciais explícitos.

Esses itens significam que a base não deve ser descartada. Um redesign total de tecnologia teria custo alto e pouco retorno. A intervenção correta é de produto, hierarquia e sistema visual.

### 5.2 Por que ainda pode parecer 3/10

Uma interface pode ter boa engenharia e ainda parecer fraca. No Mplacas, os motivos mais prováveis, observados no código, são:

1. **Card dentro de card dentro de faixa.** A Visão Geral usa uma faixa arredondada com HeroCard, QualityBanner, EnergyFlowDiagram e outro Card interno. Muitas superfícies competem antes que o usuário entenda a prioridade.
2. **Tudo tem borda, raio e sombra.** O componente `Card` é consistente, mas aplicado amplamente cria repetição visual e reduz contraste entre conteúdo principal e apoio.
3. **Hierarquia baseada em caixas, não em narrativa.** Estado, fluxo, qualidade, diagnóstico e tendência estão corretos, porém ainda se apresentam como blocos vizinhos em vez de uma história contínua.
4. **Visual corporativo genérico.** Inter + azul + cinza + cards brancos é seguro, mas pouco memorável. Falta uma assinatura solar própria.
5. **Pouca iconografia funcional.** Navegação e métricas dependem quase inteiramente de texto. Ícones bem escolhidos poderiam acelerar reconhecimento sem virar decoração.
6. **Cabeçalho e subnavegação ocupam duas faixas.** Em telas menores, o conteúdo útil começa tarde; as abas horizontais também podem parecer um site administrativo tradicional.
7. **Visão Geral ainda não mostra valor financeiro imediato.** Economia e retorno ficam no módulo Financeiro, embora “quanto economizei?” seja uma pergunta primária do proprietário.
8. **O “agora” é tecnicamente honesto, mas pouco emocional.** “Último dia com dado” existe, porém produção recente não lidera a página como nos produtos mais fortes.
9. **Títulos e explicações podem pesar.** A precisão conceitual gerou bons rótulos, mas a interface precisa distribuir detalhe por tooltip, expansão e ajuda contextual.
10. **Faltam destinos de produto.** Alertas, relatórios e configurações ainda não têm a mesma presença de navegação encontrada nos líderes.

### 5.3 Nota por dimensão

Esta nota é uma avaliação de código e arquitetura, não substitui inspeção visual renderizada.

| Dimensão | Nota estimada | Leitura |
|---|---:|---|
| Integridade e honestidade do dado | 9,2 | diferencial real do Mplacas |
| Acessibilidade estrutural | 8,5 | testes e padrões acima da média do setor |
| Arquitetura de informação | 7,5 | módulos corretos; faltam alertas/relatórios e melhor resumo |
| Visualização de dados | 7,8 | boa base SVG; precisa mais interação e menos contenção |
| Responsividade | 7,5 | malha sólida; mobile precisa ser tratado como experiência própria |
| Consistência | 8,2 | sistema coerente, mas repetitivo |
| Hierarquia visual | 5,8 | principal causa da percepção baixa |
| Personalidade e acabamento | 5,2 | visual seguro, porém genérico |
| Clareza na primeira dobra | 5,8 | há conteúdo certo, mas com excesso de superfícies |
| Utilidade operacional completa | 6,2 | central de alertas e relatórios ainda ausentes |

**Síntese:** base técnica aproximada de **7,5/10**; percepção visual provável entre **5 e 6/10** sem validar pixels. A nota subjetiva de 3/10 é compatível com frustração de acabamento, embora não descreva a qualidade da engenharia existente.

---

## 6. Direção de design recomendada

### 6.1 Conceito: “Energia clara, decisão rápida”

O produto deve parecer um centro de controle confiável, não um portal de fabricante e não uma planilha estilizada.

**Personalidade:** precisa, calma, contemporânea, solar e brasileira.  
**Promessa visual:** em cinco segundos o usuário entende estado, produção, economia e atenção.  
**Diferencial:** cada número mostra período, cobertura e confiança sem sobrecarregar a leitura.

### 6.2 Primeira dobra da Visão Geral

Proposta de composição em desktop:

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Usina / período / atualização                         ações rápidas │
├───────────────────────┬──────────────────────────┬──────────────────┤
│ ESTÁ TUDO BEM?        │ FLUXO DE ENERGIA         │ HOJE / ÚLTIMO   │
│ status + frase        │ solar → casa → rede      │ produção        │
│ saúde compacta        │ valores e direção        │ economia ciclo  │
│ alertas acionáveis    │ cobertura do dado        │ vs. esperado    │
├───────────────────────┴──────────────────────────┴──────────────────┤
│ tendência principal + alternância 7d / 30d / 90d / ciclo / 12m     │
└─────────────────────────────────────────────────────────────────────┘
```

Regras:

- uma única superfície principal, sem quatro cards aninhados;
- status e ação ficam juntos;
- o gauge de saúde deve ser menor e explicável, não competir com a manchete;
- economia do ciclo aparece como KPI resumido e leva ao Financeiro;
- atenção leva a alertas filtrados;
- qualidade e frescor aparecem como metadados compactos, expansíveis;
- mobile reorganiza para status → produção → fluxo → economia → ação.

### 6.3 Sistema visual

**Cores**

- manter azul como confiança e ação;
- introduzir um amarelo solar controlado apenas como destaque de geração, nunca para severidade;
- usar ciano/azul para rede e violeta para bateria/variável secundária;
- preservar verde/âmbar/vermelho exclusivamente para estado;
- reduzir fundos coloridos grandes; usar cor em dados, seleção e foco.

**Tipografia**

- manter Inter se performance e consistência forem prioridade;
- aumentar contraste entre display, título de módulo, título de seção e metadado;
- reduzir maiúsculas em rótulos longos;
- números principais com `tabular-nums`, peso forte e unidade subordinada;
- frases explicativas curtas; detalhe técnico em ajuda contextual.

**Superfícies**

- reservar card completo para agrupamentos semânticos;
- usar divisores e espaço em branco para métricas relacionadas;
- no máximo três níveis de superfície por tela;
- sombras mais raras; elevação apenas em elementos interativos ou flutuantes;
- raios consistentes, mas menos “pílulas” e menos caixas aninhadas.

**Iconografia**

- conjunto único, traço consistente, 16/20/24 px;
- ícones na navegação e em ações; não colocar ícone em todo KPI;
- sol, casa, rede e bateria precisam funcionar como linguagem do fluxo;
- todo ícone informativo acompanhado por texto ou nome acessível.

### 6.4 Visualizações prioritárias

1. **Fluxo de energia responsivo** com direção clara e valores que não colidem.
2. **Produção real vs. esperada** com período selecionável, tooltip e lacunas explícitas.
3. **Economia e retorno** com composição do benefício e premissas visíveis.
4. **Linha de tempo de alertas** com severidade, impacto, recomendação e estado.
5. **Comparação de usinas** quando houver múltiplas plantas: status, produção normalizada, perda e última atualização.

### 6.5 O que preservar sem negociação

- período explícito em todo indicador;
- data real do dado, não apenas hora da sincronização;
- `null` nunca transformado em zero;
- parcialidade e cobertura visíveis;
- fonte e versão para indicadores ambientais e financeiros;
- separação entre “não detectado” e “não foi possível avaliar”;
- acessibilidade WCAG 2.2 AA e alternativa tabular dos gráficos;
- nenhuma promessa de tempo real sem telemetria real.

---

## 7. Backlog priorizado para chegar ao 10/10

### P0 — validar a tela real

1. Capturar Visão Geral, Produção, Financeiro e Técnico em 1440, 768 e 390 px.
2. Registrar estados normal, alerta, erro, sem dado, parcial e carregamento.
3. Fazer auditoria pixel a pixel de alinhamento, densidade, quebra de texto e contraste percebido.
4. Medir primeira dobra: quantos pixels até a primeira informação útil e quantos blocos disputam atenção.

**Saída:** baseline visual e lista de problemas comprovados, não inferidos do JSX.

### P1 — redesign da Visão Geral

1. Remover aninhamento excessivo da faixa hero.
2. Criar um cabeçalho de contexto da usina compacto.
3. Unir estado, atenção, produção recente, fluxo e economia em uma composição única.
4. Rebaixar qualidade/frescor para metadados expansíveis sem escondê-los.
5. Tornar KPIs resumidos navegáveis para seus módulos.
6. Criar hierarquia mobile específica.

**Meta:** o usuário responde às três perguntas principais em até cinco segundos.

### P1 — fundação visual

1. Tokens de elevação, raio, espaçamento, tipografia de display e cores de fluxo.
2. Inventário de todos os usos de `Card`; classificar em card, painel, métrica ou grupo simples.
3. Adotar um conjunto de ícones consistente.
4. Definir comportamento de tooltip, popover, tabs, filtros e empty states.
5. Criar testes visuais de regressão quando o navegador estiver disponível.

### P2 — Produção

1. Seletor unificado: 7d, 30d, 90d, ciclo e 12 meses.
2. Tooltip com real, esperado, diferença, cobertura e qualidade.
3. Zoom/brush ou seleção de faixa quando houver densidade suficiente.
4. Comparação com período anterior e opção de normalização por kWp.
5. Clima como contexto somente quando a relação for tecnicamente suportada.

### P2 — Financeiro

1. Resumo visual: economia do ciclo, acumulada, ROI e payback.
2. Explicar de onde veio a economia com decomposição parte/todo.
3. Linha do tempo de economia acumulada versus investimento.
4. Premissas, cobertura e confiança sempre acessíveis.
5. CTA claro para cadastrar/ajustar investimento quando necessário.

### P2 — Técnico

1. Organizar por diagnóstico: desempenho, disponibilidade, baseline e perdas.
2. Mostrar primeiro desvios e impacto; parâmetros brutos ficam em detalhe.
3. Comparar bruto versus corrigido sem exigir que o usuário conheça a fórmula.
4. Ação recomendada ligada à causa provável e à evidência.

### P3 — novas superfícies de produto

1. Central de Alertas com novo, reconhecido, em atendimento e resolvido.
2. Relatórios mensais com visualização, download e histórico.
3. Configurações da usina e integrações.
4. Impacto ambiental com fator brasileiro, fonte e versão.
5. Comparativo multiusina para organização/instalador.

### P3 — validação

1. Teste de cinco segundos com proprietários.
2. Tarefas: encontrar produção, economia, problema ativo e período do dado.
3. SUS ou UMUX-Lite antes/depois.
4. WCAG 2.2 AA, zoom 200%, teclado e leitores de tela.
5. Core Web Vitals e orçamento de bundle.
6. Critério de aceite: nenhuma regressão na honestidade do dado.

---

## 8. Critérios objetivos de “10/10”

Uma nota 10 não deve significar “bonito para a equipe”. Deve significar:

| Critério | Meta |
|---|---|
| Compreensão inicial | 80% dos usuários identificam estado, produção e economia em até 5 s |
| Tarefa principal | encontrar um alerta ativo e a ação recomendada em até 20 s |
| Clareza temporal | 90% identificam corretamente o período de cada KPI |
| Mobile | sem rolagem horizontal da página em 320 px; controles com alvo mínimo de 44 px |
| Acessibilidade | WCAG 2.2 AA sem violações críticas |
| Desempenho | LCP < 2,5 s e INP < 200 ms no percentil 75 em produção |
| Confiabilidade | nenhum estado ausente exibido como zero; parcialidade sempre visível |
| Consistência | todos os módulos usam a mesma gramática visual e interativa |
| Satisfação | UMUX-Lite/SUS melhora de forma mensurável após o redesign |
| Regressão visual | estados críticos cobertos por snapshots em desktop, tablet e mobile |

---

## 9. Decisão recomendada

Não iniciar pelas páginas secundárias nem por uma troca ampla de tecnologia. O primeiro investimento deve ser um redesign completo e validado da **Visão Geral**, usando os dados e componentes existentes. Essa tela define a percepção do produto inteiro e permitirá consolidar o novo sistema visual antes de aplicá-lo a Produção, Financeiro e Técnico.

Sequência recomendada:

```text
baseline visual real
  → wireframe da Visão Geral
  → protótipo de alta fidelidade
  → teste rápido com usuários
  → implementação da Visão Geral
  → consolidação do design system
  → Produção
  → Financeiro
  → Técnico
  → Alertas e Relatórios
```

O benchmark não indica que o Mplacas deva copiar um concorrente. A combinação mais forte é:

- **clareza de fluxo da Huawei**;
- **diagnóstico acionável da SAJ**;
- **arquitetura por perfil do GoodWe SEMS+**;
- **processo de alertas do iSolarCloud**;
- **narrativa financeira do FoxCloud**;
- **rigor e honestidade próprios do Mplacas**.

Essa combinação pode produzir uma interface mais útil e confiável que os portais de fabricante, sem perder identidade.
