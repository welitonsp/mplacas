# ADR-084 — Conferência da distribuidora, ciclo a ciclo

## Status

**Aceito — 2026-10-24.** Pedido do dono do produto: "o usuário quer saber quanto produziu e
quanto a operadora registrou, para saber se está tendo prejuízo".

## Contexto

- O medidor da distribuidora fica no padrão de entrada e só registra o que **sai** da casa
  para a rede. O que a casa consome na hora em que as placas produzem nunca passa por ele.
  Portanto, produção do inversor − "geração" da fatura = consumo simultâneo, **não perda**.
  Mostrar só "produzi 550 × registrou 238" faria o cliente concluir, errado, que perdeu 312 kWh.
- Pesquisa de mercado (Tesla, SolarEdge, Enphase):
  - mostram o fluxo placas → casa / rede, e rede → casa;
  - exigem medidor próprio no padrão de entrada para separar casa e rede;
  - nenhuma concilia com a fatura.
- Guias brasileiros (Enel e outros):
  - usar o inversor como referência independente;
  - conferir se a injeção bate com o que sobrou depois do autoconsumo, se toda injeção virou
    abatimento e se o saldo não sumiu;
  - em caso de divergência, procurar a ouvidoria e depois a ANEEL.
- Auditoria das 26 faturas reais (set/2024–out/2026):
  - a leitura do medidor bate com o faturado em todas;
  - injeção do medidor + saldo anterior = créditos usados + saldo novo em todos os ciclos
    conferíveis, inclusive nos meses com custo de disponibilidade (o crédito não usado fica
    no saldo).

## Decisão

1. **Backend** (`reports/utility_check.py`). O `GET /reports/monthly/history` devolve, por
   ciclo, um `utility_check`, montado só com a fatura confirmada e o snapshot (ADR-038):
   - `LOSS` — prejuízo comprovado pela própria fatura: injeção do medidor + saldo da fatura
     anterior − créditos usados − saldo novo > 0,01 kWh. Devolve `missing_credits_kwh`.
   - `IMPOSSIBLE` — o medidor registrou mais envio à rede do que o inversor produziu, com
     folga de 5% para a precisão do inversor.
   - `SUSPECT` — a fração da produção enviada à rede ficou mais de 20 pontos percentuais
     abaixo da mediana dos ciclos anteriores (no mínimo 3). É suspeita, nunca prova: pode ser
     o medidor ou mais consumo durante o dia.
   - `OK` — os créditos foram conferidos e fecharam, e nada acima disparou.
   - `UNVERIFIABLE` — com o motivo em `reasons`. Nunca vira "sem prejuízo" por omissão.
     Motivos:
     - sem leitura do medidor;
     - sem a fatura do mês anterior;
     - fatura do mês anterior ambígua (mais de uma confirmada, com saldos diferentes);
     - créditos que fecham "a mais" (`CREDITS_UNBALANCED`): usados > disponíveis, por
       crédito vindo de outra UC, fatura anterior errada ou compensação lida como consumo
       total no fallback do parser.
   - Ciclos cuja produção inclui dias estimados pelo sol ou sem leitura (`PRODUCTION_ESTIMATED`)
     não rodam os níveis `IMPOSSIBLE`/`SUSPECT` e não entram na referência da fração. Pelo
     ADR-082, esse total pode ter sido elevado até a leitura do medidor, e a comparação
     seria circular.
   - A prova cita só os números do próprio `utility_check`: `meter_export_kwh` (leitura do
     medidor) e `previous_balance_kwh` (saldo de partida), nunca a injeção do snapshot.
2. **Tela** (aba Energia, "Placas × distribuidora, ciclo a ciclo"), minimalista:
   - no topo, o veredito da janela em uma frase:
     - "Sem sinal de prejuízo": em verde e **só quando todos os ciclos foram conferidos**;
     - "Sem prejuízo nos N ciclos conferidos": neutro, com "N de M" quando a conferência é
       parcial;
     - "X kWh de créditos sem explicação": com as três hipóteses (prejuízo, vencimento,
       rateio);
     - "Registro impossível";
     - "Ciclo fora do padrão";
     - "Ainda sem conferência";
   - uma legenda que explica rede × casa;
   - por ciclo:
     - uma barra fina com a composição da produção (rede registrada | casa estimada);
     - três números: Produziu (inversor), Rede (medidor ou linha da fatura) e Casa (estimado);
     - o veredito com a prova numa frase (créditos disponíveis, usados e saldo).
3. **Prejuízo em reais fica para depois.** Exige definir o valor do kWh de crédito por ciclo
   (tarifa cheia − Fio B) a partir do snapshot. Por enquanto, só kWh, sem número fabricado.

## Limitações conhecidas

- Crédito vencido (60 meses) ou enviado para outra unidade do rateio aparece como `LOSS`.
  - O resumo e a frase do ciclo dizem "sem explicação" e citam as hipóteses.
  - Próximo passo: ler da fatura o percentual de rateio ("CADASTRO RATEIO GERAÇÃO") e o saldo
    a expirar. Exige coluna nova e migration, para só afirmar prejuízo com rateio de 100%
    confirmado.
- A referência do `SUSPECT` usa só os ciclos da janela pedida, então o veredito pode mudar
  com o `limit`.
- O fallback do parser `compensated = imported` (layout sem rótulo de compensação) nunca
  foi validado com fatura real. Nesse caso a conta fecha "a mais" e cai em
  `CREDITS_UNBALANCED`.
- Sem medidor próprio de exportação, não dá para afirmar quantos kWh o medidor da
  distribuidora deixou de registrar. Os níveis 2 e 3 vigiam o fisicamente possível. A
  integração com medidor próprio é o caminho para a prova exata.
- A fração de referência usa só os ciclos da janela pedida (até 36).

## Validação

- `tests/test_utility_check.py`:
  - fatura real de out/26;
  - custo de disponibilidade de out/24;
  - crédito sumido;
  - arredondamento;
  - envio impossível e a folga do inversor;
  - suspeita e o mínimo de histórico;
  - sem conferência.
- Teste de integração em `tests/test_reports_monthly_history.py`.
- Testes de contrato e de componente no frontend, além das capturas `e2e/screenshots.spec.ts`
  (celular e desktop) e da guarda de rolagem lateral.
