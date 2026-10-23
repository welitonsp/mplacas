# ADR-081 — Reprocessar relatórios mensais como nova revisão

- **Status:** aceito
- **Data:** 2026-10-23
- **Relacionados:** ADR-038 (snapshot imutável), ADR-067 (ROI), ADR-078 (injeção real),
  ADR-079 (painel do investidor), ADR-080 (tarifa cheia)

## Contexto

O ROI e o painel do investidor somam a economia gravada no relatório mensal de cada fatura.
Esse relatório é imutável (ADR-038), e a imutabilidade é deliberada: o número que o cliente
viu não muda sozinho.

O lado ruim aparece quando o relatório foi gravado errado ou incompleto. Nesse caso, o mês
fica errado para sempre:

- faturas confirmadas antes de existir relatório ou a métrica de economia;
- ciclos sem produção ou sem tarifa naquele momento (`NO_PRODUCTION_DATA`, ADR-078);
- ciclos calculados pela fórmula antiga, pela tarifa SCEE (versão < 0.4.0, ADR-080), ou sem
  a tarifa cheia do período (`BILL_TARIFF`).

Na usina de referência, set/2026 está gravado com R$ 408,29, e o valor correto é
R$ 612,16. Mai, jun e jul/2026 não entram na soma.

## Decisão

1. **Revisão, não sobrescrita.** `monthly_report_snapshots` ganha a coluna `revision`.
   - As linhas existentes viram revisão 1 (`server_default`). A unicidade passa de
     `bill_id` para `(bill_id, revision)`.
   - Uma nova revisão entra ao lado da anterior, que nunca é alterada nem apagada.
   - Todos os leitores (ROI, investidor, histórico, último relatório) usam a maior revisão
     de cada fatura.
2. **O que é reprocessável** (`GET /reports/monthly/savings-gaps`, leitura pura):
   - `REPORT_MISSING`;
   - `REPORT_PREDATES_SAVINGS`;
   - `SAVINGS_UNAVAILABLE`, com o motivo;
   - `OUTDATED_CALCULATION`, com a economia gravada. Vale para versão < 0.4.0 ou origem
     `BILL_TARIFF`.

   Um mês calculado pela fórmula corrigida com a tarifa cheia nunca é reprocessado.
3. **Só sob pedido explícito de um ADMIN** (`POST .../reprocess`), nunca automático. Uma
   revisão só é gravada quando algo muda:
   - economia que passou a existir;
   - métrica que faltava;
   - economia ou origem da tarifa diferente.

   Clicar de novo não acumula revisões idênticas. A concorrência é decidida pela unicidade
   `(bill_id, revision)`.
4. **Auditoria.** O evento `reports.reprocess_savings` registra cada revisão criada: mês,
   fatura, número da revisão, id do snapshot e resultado.
5. **Interface.** No card "Faturas de energia" do Financeiro, o painel "Meses a recalcular"
   aparece só quando há meses.
   - Mostra o motivo de cada mês e, depois do recálculo, o antes e o depois ("economia
     passou de R$ 408,29 para R$ 612,16").
   - Diz quando um mês continua indisponível, com o motivo.

## Consequências

- O cliente vê e decide quando os números mudam. O histórico da versão anterior fica no
  banco para auditoria.
- **Downgrade da migration.** O downgrade descarta as revisões > 1. A revisão 1 original
  continua intacta.
- **Meses sem produção do inversor** continuam indisponíveis até a telemetria do período
  existir. O recálculo diz isso e não grava nada.
- **PDF/XLSX** usam o relatório mais recente da fatura mais recente, que é a revisão mais
  nova.
