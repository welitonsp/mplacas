# ADR-080 — Tarifa cheia da distribuidora na conta "sem a usina"

- **Status:** aceito
- **Data:** 2026-10-22
- **Relacionados:** ADR-067 (retorno do investimento), ADR-078 (injeção real e conta com e sem
  a usina), ADR-079 (painel do investidor)

## Contexto

A economia de um ciclo é a conta "sem a usina" menos o que a fatura cobrou. Até a versão
0.3.1, a conta "sem a usina" multiplicava o consumo da casa pelo preço da linha "CONSUMO
SCEE" da fatura.

O problema é que esse preço **não é** o que paga quem não tem usina. No SCEE, a energia
compensada é cobrada com a TE reduzida. A REH 3.544/2025 da Equatorial GO (B1 residencial
convencional, sem tributos) mostra a diferença:

| Tarifa | TUSD | TE | Total (R$/kWh) |
|---|---|---|---|
| Cheia (quem não tem usina) | 0,56767 | 0,32414 | **0,89181** |
| SCEE (energia compensada) | 0,56767 | 0,04536 | **0,61303** |

A tarifa cheia é confirmada pelas faturas reais do cliente de referência:

- A linha "CONSUMO NÃO COMPENSADO" (dez/2024 a set/2025) sai a 0,745930 sem tributos, a
  tarifa cheia da REH 3.407/2024.
- As faturas sem usina (dez/2023 a ago/2024) dão cerca de R$ 0,94/kWh com tributos.
- Consumo × tarifa cheia + iluminação reproduz o valor dessas faturas.

Com o preço SCEE, a economia de set/2026 saía R$ 408,29. Com a tarifa cheia, sai R$ 612,16.
A economia ficava subestimada em cerca de 33%, e o ROI e a TIR também.

## Decisão

1. **Tabela pública `distributor_tariffs`.** Guarda as tarifas homologadas por
   distribuidora, classe e vigência, sem tributos: a cheia e a SCEE.
   - É um dado global, fora do RLS, como `market_index_monthly`.
   - Carga inicial: Equatorial GO B1 residencial convencional, em três vigências
     (22/10/2023, 22/10/2024 e 22/10/2025). Cada valor foi conferido contra o preço impresso
     nas faturas.
2. **Pró-rata por dia, na convenção da distribuidora.** O consumo de um ciclo vai do dia
   seguinte à leitura anterior até o dia da leitura atual.
   - A média reproduz até a 6ª casa os preços impressos quando o reajuste cai no meio do
     ciclo: nov/2024 (cheia) = 0,740236; nov/2025 (SCEE) = 0,592137.
3. **Tributos da própria fatura.** Tarifa da conta = tarifa cheia × (preço com tributos ÷
   preço sem tributos da linha de consumo).
   - PIS/COFINS mudam todo mês e o ICMS é o da linha, então o fator certo é o da própria
     fatura.
   - Nunca fica abaixo do preço da própria fatura. Isso cobre o layout pré-transição, em
     que a linha já é a tarifa cheia.
4. **Sem vigência cadastrada, não há palpite.**
   - Se algum dia do ciclo não tiver vigência cadastrada, a conta usa o preço da fatura,
     como antes, e diz isso: `savings_tariff_source = BILL_TARIFF`.
   - O card mostra "pode subestimar a economia".
   - Com vigência, o card mostra "tarifa cheia da distribuidora: R$ x/kWh com impostos".
5. **Rastreabilidade.** `savings_tariff_brl_kwh` e `savings_tariff_source` entram em
   `/energy/*` e no snapshot do relatório mensal. A energia não compensada do modelo de
   conferência da fatura também passa a usar a tarifa cheia.
6. **Versão de cálculo 0.4.0.** `CORRECTED_CALCULATION_VERSION` passa a (0, 4, 0). Ciclos
   antigos aparecem no painel do investidor como estimativa a corrigir.

## Consequências

- O painel ao vivo ("Sua conta com e sem a usina") passa a mostrar a economia correta já no
  deploy.
- **Os snapshots antigos continuam com a economia subestimada.** O ROI e o painel do
  investidor somam snapshots, então eles só se corrigem com o reprocessamento de snapshots
  (em desenho). Até lá, o painel marca a estimativa como pré-correção.
- **Reajuste de 22/10/2026 ainda não cadastrado.** A ANEEL aprovou +7,36% para o B1 da
  Equatorial GO, mas os valores por componente ainda não estão na base. Ciclos que
  passarem por essa data caem no preço da fatura, com aviso, até a nova linha ser incluída.
  - A inclusão é feita por migration ou importação de arquivo: o portal da ANEEL recusa IPs
    de nuvem.
- **Só existe a classe B1 residencial convencional da Equatorial GO.** Outras distribuidoras
  e classes (tarifa branca, baixa renda) precisam de carga de dados antes da venda
  comercial.
- **Bandeiras tarifárias** ("AD. BAND.") não entram na conta "sem a usina". Isso a deixa
  conservadora nos meses de bandeira amarela ou vermelha.

## Alternativas descartadas

- **Continuar com o preço SCEE.** Descartada porque contradiz a tarifa homologada e as
  faturas sem usina do próprio cliente.
- **Ler a tarifa cheia da fatura.** Ela só aparece quando há consumo não compensado ou no
  layout pré-2024. Na maioria das faturas atuais não existe.
- **Derivar da linha "BENEFÍCIO TARIFÁRIO BRUTO SCEE".** A fórmula da distribuidora para
  essa linha não fechou com nenhuma combinação conferível.
