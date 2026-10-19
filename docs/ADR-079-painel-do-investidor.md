# ADR-079 — Painel do investidor: usina × CDI líquido (TIR, VPL, payback descontado)

## Status

**Proposto — 2026-10-19.** Fase 4 do plano de inteligência financeira (documento "MPlacas —
Inteligência do sistema: diagnóstico e plano"). Régua padrão aprovada pelo usuário: CDB a
100% do CDI, líquido de IR. A primeira revisão do agente `reviewer` não aprovou (2 P1,
7 P2). As correções e os pontos aceitos estão na seção "Revisão" abaixo.

## Contexto

O Financeiro já respondia "quanto paguei com e sem a usina" (ADR-078) e mostrava um ROI
simples (ADR-067). Mas não respondia o que um investidor brasileiro pergunta primeiro:
**a usina rendeu mais do que deixar o dinheiro no CDI?**

O sistema vai ser vendido para outros donos de usina. Então nada pode ser fixo no código,
nem o valor investido, nem o mês de ligação, nem os índices. O usuário informa os dados da
usina em "Minha usina" e as faturas no Financeiro. Os índices vêm do Banco Central.

## Decisão

### 1. Índices de mercado: tabela pública de referência `market_index_monthly`

- Fonte: SGS do Banco Central. Série 4391 = CDI acumulado no mês (% a.m.). Série 433 = IPCA
  mensal.
- Colunas: `index_code`, `reference_month` (AAAA-MM), `rate_percent`, `source`,
  `fetched_at`. Única por (`index_code`, `reference_month`). Migration `20261019_0044`.
- Só se gravam meses **fechados**. O mês corrente nunca é pedido.
- Leitura do banco primeiro. Os meses que faltam são buscados no BCB, no máximo uma
  tentativa a cada 6 h por índice, por processo. Se o BCB falhar, o painel usa o que já
  está no banco. Se faltar mês, o motivo aparece como `MARKET_DATA_UNAVAILABLE`: nunca se
  completa com um valor inventado.
- O parser rejeita payload malformado e taxa fora de −5% a 10% a.m.

### 2. Nova classe de RLS: `PUBLIC_REFERENCE_TABLES`

A tabela não tem `organization_id`: o CDI é o mesmo para todos os clientes. Classificá-la
como PLATFORM bloquearia a leitura pelos tenants. Por isso existe uma terceira classe em
`db/rls_inventory.py`, sem RLS e só com dado público. `classified_application_tables()` faz
o teste de inventário cobrir as três classes, e nenhuma tabela nova escapa de
classificação.

### 3. Saída de rede: `api.bcb.gov.br` na allowlist

O host entra no valor padrão de `MPLACAS_EXTERNAL_HTTP_ALLOWED_HOSTS`. A rota checa a
allowlist **em tempo de execução**: se o host não estiver liberado, o cliente HTTP nem é
criado e o painel trabalha só com o banco. Em produção, se a variável estiver definida
explicitamente no Render, é preciso acrescentar `api.bcb.gov.br`.

### 4. Cálculo (`intelligence/investor_metrics.py`, Decimal puro, sem I/O)

**Realizado**, desde o mês de ligação até o último mês fechado:

- Caminho A (o investimento no CDI): o valor investido rende o CDI mês a mês e paga IR
  regressivo no resgate (22,5% / 20% / 17,5% / 15%).
- Caminho B (a usina): cada economia confirmada é aplicada no CDI a partir do mês seguinte
  ao seu ciclo, com IR próprio por aporte.
- Só contam ciclos **posteriores** ao mês da ligação. A fatura do mês da ligação tem geração
  parcial. O realizado, a projeção e a cobertura usam a mesma regra.
- Se faltar algum mês de CDI, não há comparação.
- Na UI, se a cobertura (faturas confirmadas ÷ meses desde a ligação) for menor que 80%, o
  placar A × B não aparece. Mostra-se quantos meses de fatura faltam, porque comparar 1
  fatura com 12 meses de CDI mentiria por omissão.

**Projeção**, fluxo mensal em 25 anos:

- Ponto de partida: a média das economias confirmadas.
- A tarifa cresce pelo IPCA de 12 meses. Os módulos perdem 0,5% ao ano.
- O&M custa 0,5% do investimento ao ano. O inversor é trocado no ano 12, a 15% do
  investimento.
- Fio B (Lei 14.300), só para GD II (pedido de conexão a partir de 07/01/2023) e só se a
  fatura confirmada traz a tarifa do Fio B. Desconta-se a parcela adicional sobre os kWh
  compensados: 15/30/45/60/75/90% de 2023 a 2028, e **100% a partir de 2029**. É uma
  premissa conservadora, porque o art. 17 ainda não foi regulamentado.
- **Régua de longo prazo:** um CDB a 100% do CDI comprado na ligação e resgatado no mês k,
  com IR regressivo sobre o ganho **no resgate**. É o mesmo método do realizado. Não é um
  desconto de 15% na taxa a cada ano: isso funcionaria como um come-cotas permanente e
  subestimaria o CDB em cerca de 25% em 25 anos (achado P1 da revisão).
- Saídas:
  - TIR nominal e real, por bisseção;
  - patrimônio mês a mês dos dois caminhos, cada um líquido de IR no resgate. Na usina,
    cada fluxo mensal é aplicado e tem IR pelo seu próprio prazo, e custo é retirada;
  - **"CDI líquido"** = taxa efetiva de quem fica no CDB até o horizonte:
    (líquido no resgate ÷ aplicado)^(1/25) − 1. Com CDI de 14,03%, dá cerca de 13,3% ao ano.
    É a taxa de desconto do VPL e a régua contra a TIR;
  - payback simples;
  - **payback "contando o CDI"**: o primeiro mês em que o patrimônio da usina alcança o do
    CDI. É exatamente o cruzamento das linhas do gráfico;
  - economia total na vida útil.
- O CDI futuro é igual ao dos últimos 12 meses. Com menos de 12 faturas, a projeção é
  marcada como de baixa confiança, porque ainda não cobre as estações do ano.

**Versões**: snapshots calculados antes da versão 0.3.0 (ADR-078) são sinalizados
(`includes_pre_correction_cycles`). Eles podem superestimar a economia em cerca de R$ 11 por
mês.

### 5. API e UI

- `GET /energy/investor/latest?plant_id=` (ReadPlant, escopo de tenant). O backend devolve
  `unavailable_reason` com um destes valores: `INVESTMENT_NOT_REGISTERED`,
  `COMMISSIONING_DATE_MISSING`, `NO_CONSOLIDATED_SAVINGS` ou `MARKET_DATA_UNAVAILABLE`. A UI
  transforma cada um numa ação para o usuário, por exemplo "Ir para Minha usina".
- A seção "Usina × CDI" do Financeiro tem:
  - 4 indicadores: TIR, CDI líquido, VPL e payback simples/descontado;
  - um veredito em frase;
  - um gráfico de patrimônio (SVG puro, `PatrimonyLines`);
  - o bloco do realizado;
  - as premissas, em `<details>`.
- A marca "usina passa o CDI ≈ ano X" usa o **payback descontado do backend**, calculado mês
  a mês, e não uma interpolação entre pontos anuais. Assim o gráfico e o indicador nunca
  divergem.
- O gráfico mede a largura do contêiner para que o texto tenha sempre 12 px reais. No
  celular, os rótulos de ano aparecem a cada 10 anos.
- A seção é carregada sob demanda (`React.lazy`) e tem orçamento próprio de 8 kB. Isso
  mantém a página Financeiro abaixo dos 15 kB.

## Revisão (reviewer, 2026-10-19)

Corrigido:

- **P1-1.** A régua de longo prazo passou a cobrar o IR no resgate, como descrito acima.
- **P1-2.** Quando a base tem menos de 12 faturas, ou quando há ciclos pré-0.3.0, aparece uma
  faixa "Estimativa preliminar" **acima** dos indicadores. Antes o aviso ficava escondido nas
  premissas.
- **P2-3.** A cobertura tinha um erro de 1 mês: a fatura do mês da ligação entrava no
  numerador mas não no denominador. Agora ela fica fora de tudo.
- **P2-4.** Quando faltam faturas posteriores à ligação, o motivo mostrado é
  `NO_CONSOLIDATED_SAVINGS`, com texto explicando o porquê, e não mais "Banco Central
  indisponível". Investimento ≤ 0 conta como não cadastrado.
- **P2-5.** A gravação das taxas usa um savepoint. Uma corrida entre requisições
  (IntegrityError) volta a ler o banco em vez de devolver 500. O payload é deduplicado e só
  meses pedidos e ausentes são gravados; mês já gravado não é sobrescrito. Snapshot com
  valor ilegível é ignorado.
- **P2-6.** O parser exige DD/MM/AAAA com mês entre 1 e 12.
- **P2-7.** Um `market_indices_egress_blocked` é registrado (uma vez por processo) quando o
  host não está liberado. `bcb_host_allowed` exige HTTPS.
- **P3.** "0.3" equivale a "0.3.0". As janelas de 12 meses de CDI e IPCA precisam ser
  contíguas no calendário. `_serialize_investor` agora é tipada.

Aceito, e declarado na UI ou aqui:

- **P2-1.** O enquadramento GD I/GD II é estimado pela **data de ligação**, porque o modelo
  não tem a data do protocolo de acesso. A lei usa a data do pedido de conexão, e a UI diz
  isso nas premissas. O erro é conservador: pode aplicar o Fio B a uma usina GD I com
  ligação tardia. Fica como dívida acrescentar a "data do pedido de conexão" em "Minha
  usina".
- **P2-2.** Assume-se que a tarifa do Fio B impressa na fatura já reflete o percentual do
  ano (60% em 2026). A fatura real de set/2026 traz R$ 0,175126/kWh, o que implica uma tarifa
  cheia de cerca de R$ 0,29, coerente com a TUSD Fio B da distribuidora. Isso ainda deve ser
  validado com a REN da Equatorial GO. Os kWh compensados da última fatura são tratados como
  constantes, sem sazonalidade.
- **P3** restantes:
  - o throttle é por processo e por índice;
  - `date.today()` usa o fuso UTC do servidor (no pior caso, gasta uma tentativa de busca);
  - não há limite de tamanho na resposta do BCB (host confiável);
  - a degradação conta desde o mês 0, enquanto o reajuste conta desde a âncora (pequeno
    viés para menos).

## Consequências

- Todo número vem pronto do backend. O frontend não faz conta financeira.
- O painel depende de o usuário informar o investimento, o mês de ligação e as faturas. Sem
  isso, ele mostra o que falta, não zeros.
- Dívidas declaradas:
  - as premissas não são editáveis (fase 5: cenários);
  - o painel ainda não entra no PDF/XLSX nem no snapshot;
  - a regra pós-2029 do Fio B deve ser revista quando a ANEEL regulamentar o art. 17;
  - Tesouro IPCA+ e poupança como réguas secundárias ficam para a fase 5.
