# ADR-089 — "Vale a pena ampliar a usina?"

## Status

**Aceito — 2026-10-25.** Pedido do dono do produto: cruzar a produção com o que o cliente paga e
dizer, com números, se vale investir em mais placas e inversor — ou que não vale. Plano revisado
pelo `solar-domain-specialist` e pelo `financial-audit-specialist` antes da implementação; plano
corrigido aprovado pelo dono.

## Contexto

Com 12 faturas confirmadas, o sistema sabe quanto a casa puxou da rede, quanto o medidor
registrou de envio, o saldo de créditos, as tarifas (homologada ANEEL, Fio B da fatura) e o
rendimento medido da usina. Na usina do dono, o saldo de créditos chegou a 600 kWh (mar/2025) e
zerou em out/2026: o consumo cresceu e a usina deixou de cobrir — sem prejuízo da distribuidora
(a conferência do ADR-084 fecha).

## Decisão

Motor puro em `intelligence/expansion.py`, leitura em `intelligence/expansion_service.py`
(reaproveita o histórico do ADR-084, os snapshots e as faturas confirmadas — nada recalculado
fora do backend, ADR-012/038), rota `GET /energy/expansion/latest`, card na aba Dinheiro em
chunk próprio e seção nova em "Como calculamos".

1. **Falta no ano** = Σ consumo da rede − Σ envio do medidor nos 12 últimos ciclos seguidos,
   posteriores ao mês da ligação. Balanço anual porque o crédito vale 60 meses. **Não** usa
   créditos usados: quando o saldo antigo está acabando, eles escondem a falta que vai continuar.
   O mínimo faturável (30/50/100 kWh) **não** é descontado — Lei 14.300, art. 16, §1º: ele só
   pesa quando o consumo medido fica abaixo dele; vira aviso quando algum ciclo tem consumo da
   rede abaixo de 100 kWh. Exige rateio de 100% (senão o balanço teria de somar outras UCs).
2. **Veredito**, nesta ordem:
   - `INDISPONIVEL`: menos de 12 ciclos, buraco no calendário, ciclo sem leitura do medidor ou
     consumo, rateio não confirmado.
   - `CORRIGIR_ANTES` (só com dados completos e rateio de 100% — com rateio menor, a
     conferência marca `LOSS` sem prova de perda): ciclo com créditos faltando (`LOSS`) ou envio impossível nos 12 meses,
     ou produção muito abaixo do esperado nos últimos 3. Suspeita (`SUSPECT`, fração enviada à
     rede caiu) **não** bloqueia — é o sinal típico de consumo diurno maior — e vira aviso.
   - `AMPLIAR` / `NAO_VALE` / `EQUILIBRADO` pelo sinal da falta, com tolerância de 5% do
     consumo da rede no ano. O sentido (`direction`: FALTA, SOBRA ou ZERO) vem pronto do
     backend; a tela não decide pelo sinal.
3. **Tamanho** = falta ÷ rendimento anual medido (kWh/kWp/ano, só ciclos sem dia estimado ou
   provisório, mínimo 10; dias do ciclo contados como na fatura, os dois extremos inclusive), arredondado para cima em 0,1 kWp. Premissa declarada: placas na mesma direção e
   inclinação. Sem kWp cadastrado ou sem produção medida suficiente, o veredito sai sem tamanho.
4. **Inversor**: relação placas ÷ inversor depois da ampliação — até 1,30 cabe; até 1,50
   conferir o manual; acima, outro inversor. Mais de um aparelho = microinversores (ampliar é
   somar micro), sem relação da usina inteira. Sem potência do inversor, não opina.
5. **Dinheiro**: a parte ampliada pedida agora é GD II (art. 26, §2º, III) e paga a parcela do
   Fio B do art. 27 (60% 2026, 75% 2027, 90% 2028); de 2029 em diante vale o art. 17, sem regra
   da ANEEL — Fio B integral **como cenário**. Valor de 1 kWh no ano y = tarifa cheia com
   impostos − Fio B pleno × parcela(y), com Fio B pleno = Fio B da fatura ÷ parcela do ano da
   fatura. Bandeira fora; sem reajuste. Economia mensal = falta/12 × valor (limitada à falta).
   Indisponível, com motivo, quando: sem tarifa cheia homologada no último ciclo (ou ciclo
   anterior à versão 0.5.0), sem Fio B, fatura refeita não fecha (`credit_unit_value_brl` nulo),
   fatura de 2029 em diante (`TRANSITION_ENDED`: sem regra para deduzir o Fio B pleno),
   ou regime não confirmado — usina ligada antes de 2024 (protocolos de 07/01 a 07/07/2023 têm
   outra transição) ou sem data de ligação.
6. **Conflito de interesse**: veredito só do motor, não editável; "não vale" com o mesmo peso
   visual de "ampliar"; nenhum botão de orçamento; sempre "estimativa" com premissas à vista.

## Fora desta etapa

- **Retorno do investimento** (payback): exige o valor total da proposta (placas, inversor,
  instalação, homologação), com auditoria de quem informou. Seguirá o ADR-079 (fluxo mensal com
  IPCA, degradação, Fio B crescente), com "sem reajuste" como contraprova — não o ADR-067.
- **Fatura GD I + GD II**: ampliar uma usina GD I gera fatura com duas parcelas, que o parser
  hoje recusa (uma linha de consumo e uma de injeção). Entra quando surgir o primeiro caso.
- Rendimento para outra orientação (PR mediano × POA, ADR-057/068) e potência do módulo para
  contar placas.

## Consequências

- O cliente recebe uma resposta honesta também quando **não** vale ampliar.
- Limitações declaradas na tela: orientação igual, critério de divisão GD I/GD II da
  distribuidora não verificado, cenário de 2029+, pedido de conexão e padrão de entrada.


## Etapa 2 — retorno da proposta (2026-10-28)

Decisão do dono: **guardar** o valor da proposta na usina.

- Migration 0050: `plants.expansion_proposal_brl` (> 0), `expansion_proposal_includes_inverter`
  e `expansion_proposal_recorded_on` (data do registro, gravada pelo servidor). Rota
  `PATCH /plants/{id}/expansion-proposal`, só ADMIN da organização (404 fora do escopo),
  auditada como `plant.expansion_proposal_updated`; `amount_brl: null` apaga.
- O retorno reaproveita `project()` do ADR-079 (não o payback nominal do ADR-067, que ignora o
  Fio B): economia de partida = falta ÷ 12 × (tarifa cheia com impostos − Fio B da fatura),
  sem bandeira; reajuste pelo IPCA de 12 meses; degradação, O&M, troca do inversor; Fio B da
  parte nova subindo a partir do ano da fatura (`commissioned_on` = hoje: GD II). Mostra o prazo
  com IPCA, **sem reajuste** (contraprova) e contando o CDI líquido.
- Não calcula (`NOT_APPLICABLE`) fora de `AMPLIAR` com valor em reais; `PROPOSAL_MISSING`;
  `INVERTER_NOT_IN_PROPOSAL` quando a ampliação pede inversor novo e a proposta não o inclui;
  `MARKET_DATA_UNAVAILABLE` sem 12 meses seguidos de CDI/IPCA.
