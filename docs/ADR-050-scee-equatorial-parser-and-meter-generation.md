# ADR-050 - Parser SCEE Equatorial Goias e reconciliacao de tres pontas

## Status

Aceito.

## Contexto

O parser de faturas em `src/mplacas/billing/parser.py` foi escrito com padroes regex
genericos que nao correspondiam ao layout real das faturas SCEE da Equatorial Goias.
Validado contra uma fatura real (junho/2026), 9 dos 11 campos obrigatorios falharam na
extracao, tornando o pipeline de billing inoperante para a distribuidora principal do projeto.

Alem disso, o layout SCEE expoe um campo nao previsto no modelo: `GERACAO CICLO KWH`,
a geracao medida pelo medidor de geracao da concessionaria. Esse valor e diferente de
`injected_kwh` (energia injetada na rede apos autoconsumo) e permite uma reconciliacao
de tres pontas: producao medida na origem (NEPViewer) vs geracao no medidor vs injecao
compensada — util para identificar perdas e divergencias de medicao.

## Decisao

1. Adicionar padroes SCEE reais como primeira opcao em `_FIELD_PATTERNS` para todos os
   campos que possuem regex compativel. O fallback generico permanece como segunda opcao,
   preservando faturas processadas no formato sintetico anterior.

2. Implementar tres funcoes auxiliares para campos que nao cabem em regex independentes:
   - `_extract_scee_reading_dates`: extrai a linha de quatro datas (anterior, atual, dias,
     proxima) e converte a data de leitura atual para `cycle_end` exclusivo menos um dia,
     mantendo a semantica inclusiva do dominio sem alterar `validate()`.
   - `_parse_reference_month_scee`: converte abreviacao de mes em portugues (jan..dez)
     para o formato YYYY-MM do dominio; falha fechado para abreviacoes desconhecidas.
   - Extracao do total mascarado (`R$**********80,21`) via padrao SCEE-first que remove
     os asteriscos antes da conversao numerica.

3. Adicionar `generation_cycle_kwh: Decimal | None = None` como campo opcional de
   `UtilityBill`. Nullable porque faturas processadas via fallback generico nao o possuem.
   O campo e validado (nao-negativo) apenas quando presente.

4. Adicionar coluna `generation_cycle_kwh Numeric(12,3) NULL` em `utility_bills` via
   migration Alembic sem backfill. Registros legados permanecem NULL — honesto e sem
   inventar dado ausente.

5. Propagar o campo por toda a fronteira de leitura: `UtilityBillRecord`, `create_pending`,
   `_to_confirmed_bill`.

6. Estender `BillingReconciliation` com tres campos opcionais, presentes apenas quando
   `bill.generation_cycle_kwh` nao e None:
   - `generation_cycle_kwh`: valor bruto do medidor.
   - `meter_vs_injection_delta_kwh`: geracao no medidor menos injecao compensada
     (autoconsumo visto pela concessionaria).
   - `origin_vs_meter_delta_kwh`: producao NEPViewer menos geracao no medidor
     (divergencia origem-medidor, ex: perdas ou descasamento de fronteira de medicao).
   Quando o campo e None, os tres saem None — fail closed, sem estimativa.

## Consequencias

### Positivas

- O pipeline de billing passa a funcionar com o layout real da Equatorial Goias SCEE.
- Faturas no formato sintetico anterior nao sao afetadas (fallback intacto).
- O modelo suporta reconciliacao de tres pontas sem quebrar a reconciliacao de duas
  pontas existente.
- A migration e segura para producao: apenas ADD COLUMN nullable, sem backfill.

### Negativas

- O campo `generation_cycle_kwh` exige que a fatura PDF contenha a secao de medicao
  de geracao; faturas de UCs sem medicao separada continuarao com o campo None.
- A logica de alertas sobre divergencia origem-medidor foi adiada (escopo fora deste ADR).

## Validacao

A entrega e coberta por:

- testes do parser SCEE contra fixture real anonimizada (8 casos);
- testes de regressao do parser sintetico (3 casos pre-existentes);
- testes de reconciliacao de tres pontas e ausencia de campo (5 casos);
- testes de repository e read_repository com round-trip do campo;
- teste de contrato da migration (upgrade/downgrade);
- Ruff;
- Mypy (modulo billing);
- Pytest (suite de billing completa, 22 casos).
