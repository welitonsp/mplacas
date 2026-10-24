# ADR-085 — Bandeira na conta "sem a usina" e créditos externos fora da economia

## Status

**Aceito — 2026-10-24.** Item 1 do plano aprovado pelo dono depois da revisão dos cálculos
pelas regras da ANEEL. Versão de cálculo **0.5.0**.

## Contexto

A revisão das 26 faturas reais (set/2024–out/2026) mostrou que o modelo reproduz a fatura
no centavo, mas a economia tinha dois desvios.

1. **A bandeira ficava fora da conta "sem a usina".** Sem as placas, todo o consumo pagaria
   a bandeira do ciclo. Hoje a fatura só a cobra sobre a energia não compensada (linha "ADC
   BANDEIRA …"). Em mês de bandeira, a economia saía subestimada: cerca de R$ 7 em out/26
   (amarela).
2. **Créditos que não vêm das placas entravam como economia.** A economia é "conta sem a
   usina − componente de energia pago". A compensação por falta de luz (DIC/FIC/DMIC/DICRI,
   PRODIST Módulo 8) e o Bônus de Itaipu baixam o valor pago, e por isso eram atribuídos à
   usina. Foram R$ 57,28 em dois anos (jan/25 R$ 30,38, fev/25 R$ 6,38, ago/25 R$ 20,17,
   ago/26 R$ 0,35).

## Decisão

1. **O leitor da fatura grava dois campos** (migration `20261024_0048`, nullable, sem
   backfill):
   - `flag_tariff_brl_kwh`: soma dos preços **com tributos** das linhas "ADC BANDEIRA …".
     Quando duas cores caem no mesmo ciclo, cada uma vem numa linha com o preço pró-rata. O
     preço já carrega o fator de tributos da própria linha (ICMS/PIS/COFINS do mês).
     Implausível (> R$ 0,50/kWh) vira `NULL`.
   - `non_energy_credits_brl`: soma, em valor absoluto, das linhas negativas de compensação
     por interrupção e de Bônus de Itaipu.
2. **Motor de cálculo** (`energy_engine.analyze_energy_cycle`):
   - conta sem a usina = consumo total × (tarifa cheia homologada × tributos da fatura +
     bandeira) + iluminação pública;
   - componente de energia pago = total − iluminação + créditos externos. O dono teria esses
     créditos com ou sem usina;
   - conferência do modelo: a bandeira entra sobre a energia não compensada e os créditos
     externos são abatidos.
3. **Bônus de Itaipu: decisão conservadora.** Sai da economia. Ele só é pago a quem consome
   pouco da rede, e as placas ajudam nisso, mas é um crédito do governo, não energia gerada.
   Tirar mantém a economia como piso.
4. **Sem a linha de bandeira, nada é presumido.** A fatura não traz a bandeira quando toda
   a energia foi compensada ou quando ela é verde. Nesses casos a bandeira fica fora, como
   antes.
5. **Relatórios congelados (ADR-038):** relatórios anteriores à 0.5.0 só aparecem em "Meses
   a recalcular" se a fatura **tem** bandeira ou créditos externos gravados. Sem esses
   dados, refazer daria o mesmo número. Faturas já gravadas ganham os campos quando o PDF é
   reimportado (`billing/completion.py`).
6. **Transparência:** o snapshot e o `/energy/executive/latest` expõem os dois valores. Em
   "Detalhes da fatura", a aba Dinheiro diz que a bandeira foi incluída e quanto de crédito
   externo ficou fora.

## Validação

- **Faturas reais:** o leitor encontra bandeira em dez/24, ago/25, set/25 e out/26, e
  créditos externos em jan/25, fev/25, ago/25 e ago/26, idênticos à auditoria manual.
- **Fatura recalculada × fatura real:** com a fórmula nova, todas as faturas com Fio B
  fecham com diferença de **R$ 1,31**, a parcela retroativa do Fio B (22 parcelas,
  legítima), com duas exceções:
  - dez/24 e jan/25 ainda deixam o ICMS sobre a energia compensada, cobrado pela regra da
    época;
  - set/25 fica em R$ 1,32, diferença de arredondamento.
- **Testes:**
  - `tests/test_economia_bandeira_creditos.py`: leitor; fórmula com a fatura de out/26
    (diferença de R$ 1,31); créditos externos não viram economia; quando um relatório fica
    desatualizado;
  - contrato da migration e da página Dinheiro.

## Limitações

- A bandeira de ciclos 100% compensados não aparece na fatura. Para incluí-la, seria
  preciso cadastrar as bandeiras homologadas mês a mês (ANEEL). Fica para depois.
- O crédito de um kWh guardado (valor do saldo) continua sem a bandeira, que varia mês a
  mês.
