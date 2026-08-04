# Benchmark competitivo de UI/UX — Mplacas

**Data:** 2026-08-04
**Documento complementar de:** `docs/UI_UX_AUDIT_2026-08-04.md`

---

## 0. LIMITAÇÃO METODOLÓGICA — LEIA ANTES DE USAR ESTE DOCUMENTO

**Não houve acesso à internet durante esta auditoria.** Nenhuma interface de concorrente
foi aberta, capturada ou verificada em 2026-08-04.

O conteúdo abaixo é, portanto:

- **baseado em conhecimento de treinamento até meados de 2026**, sujeito a defasagem;
- restrito a **padrões estruturais amplamente documentados e estáveis** desses produtos —
  não a detalhes de layout, cores, textos de interface ou funcionalidades recentes;
- **deliberadamente conservador**: onde não havia segurança, o item foi omitido em vez de
  preenchido. Não há nenhuma característica inventada neste documento.

**Consequência prática:** este benchmark **não deve ser usado como especificação**. Serve
para extrair princípios e identificar lacunas prováveis. Antes de qualquer decisão de
produto derivada dele, os itens marcados com **[VERIFICAR]** precisam ser confirmados por
alguém com acesso real aos produtos.

---

## 1. Referências consideradas

### Concorrentes diretos (portais de monitoramento fotovoltaico)

- **SolarEdge Monitoring** — portal do fabricante de inversores/otimizadores.
- **Enphase Enlighten** — portal do fabricante de microinversores.
- **Huawei FusionSolar** — portal do fabricante de inversores.
- **Fronius Solar.web** — portal do fabricante de inversores.
- **SMA Sunny Portal / ennexOS** — portal do fabricante de inversores.
- **SOLARMAN Smart** — plataforma white-label muito usada no Brasil.

### Referências adjacentes de qualidade de interação (não concorrentes)

- **Apple Home / Health / Weather** — divulgação progressiva, hierarquia, restrição visual.
- **Stripe Dashboard** — densidade de dado financeiro com hierarquia clara.
- **Linear** — velocidade percebida, tipografia disciplinada, restrição cromática.

---

## 2. Princípios estruturais observáveis no setor

Estes são padrões suficientemente universais entre os portais fotovoltaicos para serem
afirmados com segurança razoável. Ainda assim, **[VERIFICAR]** antes de usar como requisito.

### 2.1 O "agora" lidera a página

Praticamente todos os portais do setor abrem com **potência instantânea e energia do dia**.
É a primeira coisa que o dono da usina procura ao abrir o app.

**Como o Mplacas se posiciona:** o Mplacas é estruturado em torno do **ciclo de faturamento
mensal**, não do dia. Não existe "produção de hoje" em destaque; o dado mais recente é o
último ponto do gráfico de 90 dias.

**Princípio a extrair — não o layout:** o produto deve responder a pergunta temporal mais
imediata do usuário antes das agregadas. Isso **não** significa copiar o mostrador de
potência instantânea: o Mplacas trabalha com dado diário consolidado e auditável, e fingir
tempo real seria desonesto. Significa dar destaque explícito ao **último dia com dado**,
com sua data — algo que o `DataFreshness` já sabe calcular.

### 2.2 Alternância de período é um controle de primeira classe

Dia / mês / ano / total é praticamente universal como seletor no topo do gráfico principal.

**Mplacas:** janela de 90 dias fixa no código (achado P1-07).

### 2.3 Diagrama de fluxo de energia é padrão de mercado

Sol, inversor, casa e rede (e bateria, quando existe) formam a representação canônica.

**Mplacas:** `EnergyFlowDiagram` já implementa Produção, Autoconsumo/Exportada, Rede e
Consumo, com barras de composição e valores em kWh. **Este é um item em que o Mplacas já
está no padrão do setor**, e a versão dele é mais honesta que a média porque separa
explicitamente autoconsumo de exportação em ambos os lados.

### 2.4 Indicadores ambientais são onipresentes — e frequentemente errados

CO2 evitado, árvores equivalentes e afins aparecem em praticamente todos os portais.
Também é notório no setor que o fator de emissão usado costuma ser importado de matrizes
elétricas de base térmica, superestimando o resultado para a matriz brasileira.

**Mplacas:** ADR-066 já enfrenta exatamente esse problema, decidindo pelo fator oficial
MCTI/SIRENE do SIN, versionado. **O módulo existe** (`intelligence/environmental.py`) mas
não tem endpoint nem interface. É uma oportunidade de **diferenciação por honestidade**.

### 2.5 ROI e payback são o gancho comercial

Retorno do investimento é o indicador que o dono da usina mais cita. **[VERIFICAR]** a
forma exata em cada produto.

**Mplacas:** ADR-067 aceito, Etapas A e B implementadas (economia no snapshot, migration do
CAPEX), C/D/E pendentes. O desenho do ADR-067 — com `cycles_counted` vs. `cycles_expected`
explícitos — é mais rigoroso que a prática comum de extrapolar payback a partir de poucos
meses.

### 2.6 Alertas têm superfície própria

Portais do setor têm lista de alertas/eventos com histórico, severidade e estado
(novo/reconhecido/resolvido).

**Mplacas:** existe ledger de alertas no banco e entrega por Telegram (ADR-015 a 018, 040),
mas **não existe endpoint de leitura nem tela**. É a lacuna de módulo mais clara.

### 2.7 Divulgação progressiva por nível de usuário

Os portais mais maduros separam a visão do proprietário da visão do instalador/O&M — a
segunda com PR, disponibilidade, curvas de string, perdas.

**Mplacas:** já faz essa separação conceitualmente correta com a
`TechnicalPerformanceSection` própria. **Mas ela está sempre expandida na mesma página**,
sem colapso nem separação por perfil — misturando os dois públicos.

---

## 3. Onde o Mplacas já é superior (com evidência no próprio código)

Estes pontos não dependem de verificação externa — são propriedades verificáveis do Mplacas
que, pela natureza do que fazem, raramente aparecem em portais de fabricante:

1. **Motivos tipados de indisponibilidade.** `NO_PERFORMANCE_RESULTS`,
   `NO_PERFORMANCE_HISTORY`, `REFERENCE_YEAR_INCOMPLETE`, `NO_LOSS_ASSESSMENTS`,
   `TARIFF_NOT_AVAILABLE` — cada um com mensagem específica em pt-BR. O padrão comum do
   setor é o card vazio, o traço mudo ou o zero.
2. **Proibição estrutural de zero fabricado.** `EstimatedSavingsCard` nunca renderiza
   R$ 0,00 quando a tarifa não está registrada — mostra o motivo.
3. **Selo "Parcial" com escopo correto.** Aplicado só aos indicadores derivados do dado
   diário; `imported_kwh`/`injected_kwh` vêm da fatura confirmada e **não** são marcados.
4. **Frescor igual a data do dado, não hora do fetch.** `DataFreshness` responde "meu dado
   está atualizado até quando?".
5. **Taxonomia de perdas com nível de evidência.** Oito categorias com
   `LIKELY`/`POSSIBLE`/`NOT_DETECTED`/`NOT_ASSESSABLE` e `limitation` textual. Declarar
   "não foi possível avaliar" em vez de estimar é epistemicamente mais rigoroso do que a
   prática usual de atribuição de perdas.
6. **PR bruto e PR corrigido por temperatura lado a lado**, com explicação do que cada um
   isola.
7. **Disponibilidade de *reporte*, explicitamente não confundida com uptime de
   equipamento** — o card diz isso no próprio texto.

**Leitura estratégica:** o eixo competitivo natural do Mplacas **não é** "mais bonito que o
portal do fabricante". É **auditabilidade e honestidade do dado**. Toda decisão de UI
deveria reforçar esse eixo, não diluí-lo.

---

## 4. Matriz comparativa

Legenda: **A** = atende bem, **P** = parcial, **X** = ausente, **?** = não verificável sem
acesso à internet.

Colunas de concorrentes usam **?** sempre que o item depende de detalhe de interface que não
pode ser afirmado sem inspeção real. Isso é intencional: uma matriz cheia de afirmações não
verificadas seria pior que uma matriz honestamente incompleta.

| Critério | Mplacas (verificado no HEAD) | Portais de fabricante (setor) | Observação |
|---|---|---|---|
| Visão executiva de saúde | **A** — `HeroCard` com status, headline e índice 0-100 | ? | Índice de saúde composto é incomum no setor |
| Produção "agora"/hoje | **X** — produto orientado a ciclo mensal | **A** (padrão universal) | Ver 2.1 |
| Produção do ciclo | **A** | ? | |
| Produção esperada | **P** — existe, mas é média achatada (P1-02) | ? | |
| Fluxo energético | **A** — `EnergyFlowDiagram` | **A** (padrão universal) | Paridade |
| Histórico | **P** — 90 dias fixos (P1-07) | **A** (dia/mês/ano/total) | Maior lacuna de interação |
| Comparativo temporal | **P** — só ciclo vs. ciclo anterior | ? | |
| Diagnósticos com causa e ação | **A** — severidade + `recommended_action` | ? | Provável vantagem do Mplacas |
| Financeiro | **P** — presente mas mal hierarquizado (P2-04) | ? | |
| ROI / payback | **X** | **A** (padrão comercial) | ADR-067 C/D/E pendentes |
| Impacto ambiental (CO2) | **X** na UI (módulo pronto) | **A**, frequentemente com fator inflado | Oportunidade de diferenciação honesta |
| Alertas (central) | **X** — só entrega por Telegram | **A** | Exige endpoint novo |
| Relatórios / exportação | **X** na UI (backend completo) | ? | Backend já suporta CSV/PDF/XLSX |
| Desempenho técnico (PR, yield, perdas) | **A** — acima da média | ? (geralmente só em perfil instalador) | Ponto forte |
| Frescor / completude do dado | **A** — provável melhor da categoria | ? | Ponto forte |
| Mobile | **P** — funciona, mas régua do gráfico dessincroniza (P1-05) e não há ícone de tela inicial (P2-10) | ? (a maioria tem app nativo) | |
| Acessibilidade | **P** — estrutura boa, contraste reprova (P1-03) | ? | |
| Confiança percebida | **A** no dado, **P** na casca (favicon 404, sem identidade de usina) | ? | Assimetria a corrigir |
| Configuração da usina pelo usuário | **X** (backend pronto) | **A** | |
| Multi-usina | **X** — `VITE_PLANT_ID` fixo no build | **A** | ADR-052 já aponta o caminho |

---

## 5. Princípios extraídos (o que adotar — sem copiar layout)

1. **Responder primeiro a pergunta temporal mais imediata.** Para o Mplacas isso é o
   **último dia com dado**, com a data explícita — não potência instantânea inventada.
2. **Período é controle, não constante.** Seletor de janela é requisito, não refinamento.
3. **Divulgação progressiva por público.** Proprietário vê saúde, produção, custo e ação;
   camada técnica colapsável ou em página própria.
4. **Indicador ambiental como prova de rigor, não de marketing.** Publicar com fator, fonte
   e versão visíveis vira diferencial exatamente porque o setor não faz isso.
5. **Alertas precisam de casa própria.** Notificação efêmera por Telegram não substitui
   histórico consultável com severidade e estado.
6. **Não copiar densidade cromática.** Vários portais do setor usam gradientes e paletas
   amplas. O Mplacas fez a escolha correta ao restringir cor a função semântica — **isso
   deve ser preservado**, não "modernizado".
7. **Não adicionar biblioteca de gráficos por padrão de mercado.** Os 86 kB gzip atuais são
   uma vantagem real de performance percebida. Só reconsiderar se um requisito concreto de
   visualização não puder ser atendido em SVG.

---

## 6. O que este documento NÃO autoriza

- Não autoriza afirmar, em material de produto, que o Mplacas é "melhor que o concorrente X"
  em qualquer critério marcado com **?**.
- Não autoriza copiar layout, paleta ou nomenclatura de nenhum produto citado.
- Não autoriza tratar as linhas **[VERIFICAR]** como fatos.
