# ADR-056 — Tarifa é atributo da fatura, não da usina

## Status

Aceito.

## Contexto

O Mplacas vai construir uma camada financeira (economia em R$) sobre o pipeline de
billing (ver ADR-050). O insumo central dessa camada é a tarifa em R$/kWh — sem ela
não é possível converter kWh economizado em reais economizados.

O texto da fatura Equatorial Goiás já contém a tarifa em três formas, na mesma linha
de consumo SCEE e na linha do Fio B (Parcela de Injeção com desconto):

```
CONSUMO SCEE kWh 278,00 0,799059 222,14 9,51 222,14 19% 42,21 0,613030
                        ^^^^^^^^ com tributos              ^^^^^^^^ sem tributos
PARC INJET S/DESC - 28,57% - GD II 2 kWh 278,00 0,175126 48,69 0,175126
                                                ^^^^^^^^ Fio B R$/kWh
```

Nas três faturas reais confirmadas em produção, o valor "com tributos" variou mês a
mês: `0,774023` (mai/2026), `0,799059` (jun/2026), `0,814841` (jul/2026) — uma
variação de ~5% em três ciclos consecutivos. Já o valor "sem tributos" (`0,613030`)
e o Fio B (`0,175126`) se mantiveram estáveis nas três faturas observadas, mas nada no
layout da fatura ou na regulação tarifária garante que permaneçam assim — reajustes de
bandeira tarifária, bandeiras vermelhas, revisões tarifárias periódicas da distribuidora
e mudanças de alíquota de ICMS/PIS/COFINS afetam exatamente esses valores.

A pergunta de design foi: onde esses três valores devem morar? Duas opções óbvias:

1. Como configuração da usina (`Plant` ou uma tabela de tarifas associada à usina),
   com um valor "vigente" atualizado manualmente quando muda.
2. Como campo da própria fatura (`UtilityBill`), um valor por ciclo de faturamento.

## Decisão

1. A tarifa é um atributo de `UtilityBill`, não de `Plant` (nem de qualquer outra
   configuração de usina). Três campos novos, opcionais, seguindo exatamente o padrão
   já estabelecido por `generation_cycle_kwh` (ADR-050):
   - `tariff_with_taxes_brl_kwh: Decimal | None = None`
   - `tariff_without_taxes_brl_kwh: Decimal | None = None`
   - `wire_b_tariff_brl_kwh: Decimal | None = None`

   Todos `Numeric(12, 6)` no banco (seis casas decimais — a fatura real expõe a tarifa
   com essa precisão, ex: `0,799059`; truncar para `Numeric(12,3)`, precisão usada por
   `generation_cycle_kwh` para kWh, perderia informação monetária real).

2. `UtilityBill.validate()` valida não-negatividade apenas quando o campo está
   presente — mesma semântica de `generation_cycle_kwh`: nenhum valor é inventado
   quando ausente, e nenhuma fatura antiga/sintética é invalidada retroativamente.

3. O parser (`parser.py`) extrai os três campos da linha `CONSUMO SCEE kWh` (tarifa com
   e sem tributos) e da linha `PARC INJET ... kWh` (Fio B), como padrões SCEE-first em
   `_FIELD_PATTERNS`. Nenhum dos três é obrigatório: uma fatura no formato genérico
   (fallback sintético pré-SCEE) continua parseando normalmente com os três campos
   `None` — o pipeline de billing não pode quebrar por um dado financeiro adicional
   que só o layout SCEE expõe.

4. A razão para modelar a tarifa na fatura e não na usina: **a tarifa é um dado medido,
   auditado, específico do ciclo de faturamento — não uma configuração operacional da
   planta.** Ela já vem impressa no mesmo documento que o Mplacas usa como fonte de
   verdade para consumo, injeção e valores em reais (ADR-006 — determinístico antes da
   IA). Modelá-la como configuração da usina exigiria:
   - Um processo manual de atualização (alguém digitar a nova tarifa toda vez que ela
     muda), que diverge da fonte auditável e pode ficar desatualizado silenciosamente.
   - Escolher um valor "vigente" para aplicar retroativamente a faturas antigas — mas a
     tarifa de maio não é a de junho; aplicar a tarifa vigente de hoje ao cálculo de
     economia de um mês passado inventaria um número que não é o que o cliente
     realmente pagou.

   Ou seja: tratar a tarifa como config da usina trocaria um dado medido por um dado
   estimado, exatamente o tipo de invenção que ADR-006 e ADR-050 (fail closed, sem
   estimar o que não foi extraído) existem para evitar.

5. Migration Alembic `20260801_0028`: três `ADD COLUMN Numeric(12, 6)` nullable em
   `utility_bills`, sem backfill. Registros antigos permanecem `NULL` — honesto, sem
   inventar tarifa retroativa para faturas já confirmadas antes desta mudança.

6. Escopo explicitamente fora deste ADR: cálculo de economia em R$ usando esses campos.
   Essa é a próxima etapa (PR seguinte), que consumirá `tariff_with_taxes_brl_kwh` e/ou
   `wire_b_tariff_brl_kwh` para converter kWh evitado em R$ economizado — decisão de
   qual tarifa usar em qual fórmula fica para esse PR.

## Consequências

### Positivas

- A tarifa usada no cálculo de economia (PR seguinte) será sempre a tarifa realmente
  cobrada naquele ciclo, não uma aproximação ou um valor "vigente" desatualizado.
- Nenhum processo manual de configuração é necessário — a tarifa entra no sistema pelo
  mesmo caminho que todo o resto do billing: parser determinístico da fatura real.
- Faturas históricas confirmadas antes desta mudança continuam válidas, com os três
  campos `NULL` (sem tarifa retroativa inventada).
- O padrão replica exatamente `generation_cycle_kwh` (ADR-050): time de manutenção não
  precisa aprender uma convenção nova.

### Negativas

- Faturas no formato sintético genérico (fallback) nunca terão tarifa — qualquer
  cálculo de economia dependerá exclusivamente do layout SCEE real. Isso é aceitável
  porque as 3 faturas em produção já são todas SCEE, mas limita retroatividade para
  qualquer integração futura com outra distribuidora que não exponha esses campos.
- Sem tarifa "vigente" configurável, não há como estimar economia para um ciclo cuja
  fatura ainda não foi processada (ex: projeção do mês corrente antes do fechamento).
  Esse trade-off é aceito conscientemente: o projeto prioriza dado medido sobre dado
  projetado (ADR-006).

### Risco estrutural: ancoragem por posição ordinal

Os três campos de tarifa são extraídos **contando posições numéricas** na linha, e não
capturando o primeiro número após um rótulo. Isso os torna estruturalmente mais frágeis
que os campos SCEE já existentes (`imported_kwh`, `injected_kwh`,
`generation_cycle_kwh`), que usam ancoragem rasa — o valor vem imediatamente após um
rótulo textual estável.

O modo de falha é o pior possível para dado financeiro: **miscaptura silenciosa**. Se a
Equatorial alterar o layout e remover uma coluna intermediária, o padrão de
`wire_b_tariff_brl_kwh` não falha — ele captura `48,69` (o total em R$ da linha) em vez
de `0,175126` (a tarifa em R$/kWh). Sem mitigação, esse número entraria no banco, passaria
por uma `validate()` que só rejeitava negativos, e viraria uma economia fabricada
apresentada ao usuário como fato.

Mitigação adotada: `UtilityBill.validate()` rejeita qualquer tarifa fora da faixa
plausível `(0, 5]` R$/kWh. O limite superior é generoso (mais de 6× a tarifa residencial
brasileira real com tributos, ~R$ 0,80/kWh em 2026), mas suficiente para pegar qualquer
deslocamento de ordem de magnitude. Consequência deliberada: uma miscaptura **rejeita a
fatura inteira no intake**, em vez de gravar dado plausível-mas-errado. O operador vê o
erro e reporta; o sistema não inventa número. Isso segue o princípio de falhar fechado já
estabelecido no ADR-006 e no ADR-050.

Uma alternativa considerada e descartada: reescrever os padrões para ancoragem semântica
por rótulo. Descartada porque as colunas de tarifa não têm rótulo textual próprio na linha
— elas são posicionais no layout impresso da Equatorial. A guarda de faixa é a defesa
disponível, não a ideal; se a distribuidora publicar um layout com rótulos, este ADR deve
ser revisto.

## Validação

A entrega é coberta por:

- testes do parser extraindo os três campos das três faturas reais (mai/jun/jul 2026)
  via fixture parametrizada com os valores reais de tarifa;
- teste de regressão do parser: fatura SCEE sem as colunas de tarifa (formato usado
  antes desta mudança) continua parseando com os três campos `None`;
- testes de `UtilityBill.validate()`: rejeita valor negativo quando presente, aceita
  ausência (`None`) e aceita valores reais válidos;
- testes da guarda de faixa: rejeita zero, rejeita valor acima do limite plausível,
  rejeita especificamente um total monetário capturado por engano (`48,69`), aceita o
  valor exatamente no limite, e aceita as três tarifas reais de produção;
- teste de ponta a ponta do modo de falha: uma linha `PARC INJET` com a coluna de
  quantidade ausente (o cenário de deslocamento descrito acima) é rejeitada no intake em
  vez de persistir o total monetário como tarifa;
- testes de round-trip em `UtilityBillRepository.create_pending` e
  `ConfirmedBillReadRepository` (persistência e leitura preservam os três campos, com e
  sem valor);
- teste de contrato da migration `20260801_0028` (presença de `batch_alter_table`,
  `Numeric(12, 6)`, `nullable=True`, ausência de `drop_column` no upgrade e de
  `add_column` no downgrade);
- verificação manual de round-trip da migration (upgrade → downgrade → upgrade) contra
  SQLite, já que o projeto roda SQLite em desenvolvimento;
- Ruff, Mypy, Pytest (suíte completa).
