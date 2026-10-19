# ADR-079 — Painel do investidor: usina × CDI líquido (TIR, VPL, payback descontado)

## Status

**Proposto — 2026-10-19.** Fase 4 do plano de inteligência financeira (documento "MPlacas —
Inteligência do sistema: diagnóstico e plano"). Régua padrão aprovada pelo usuário: CDB a
100% do CDI, líquido de IR. Vai passar pelo agente `reviewer` antes do merge, porque cria
migration e cálculo financeiro.

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
- Saídas:
  - TIR nominal e real, por bisseção;
  - VPL descontado pelo CDI × (1 − 15%);
  - payback simples e descontado;
  - economia total na vida útil;
  - patrimônio anual dos dois caminhos.
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

## Consequências

- Todo número vem pronto do backend. O frontend não faz conta financeira.
- O painel depende de o usuário informar o investimento, o mês de ligação e as faturas. Sem
  isso, ele mostra o que falta, não zeros.
- Dívidas declaradas:
  - as premissas não são editáveis (fase 5: cenários);
  - o painel ainda não entra no PDF/XLSX nem no snapshot;
  - a regra pós-2029 do Fio B deve ser revista quando a ANEEL regulamentar o art. 17;
  - Tesouro IPCA+ e poupança como réguas secundárias ficam para a fase 5.
