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
   - **Um mês que já tinha economia nunca a perde.** Se o recálculo de hoje não consegue
     calcular (ex.: telemetria antiga podada pela retenção do ADR-048), nada é gravado e a
     revisão anterior continua valendo.
4. **Auditoria.** O evento `reports.reprocess_savings` registra cada revisão criada: mês,
   fatura, número da revisão, id do snapshot, causa e economia antes e depois.
   - O recálculo roda numa transação só: um erro em qualquer fatura desfaz tudo, inclusive
     o evento.
5. **Interface.** No card "Faturas de energia" do Financeiro, o painel "Meses a recalcular"
   aparece só quando há meses.
   - Mostra o motivo de cada mês e, depois do recálculo, o antes e o depois ("economia
     passou de R$ 408,29 para R$ 612,16").
   - Diz quando um mês continua indisponível, com o motivo.

## Consequências

- O cliente vê e decide quando os números mudam. O histórico da versão anterior fica no
  banco para auditoria.
- **Downgrade da migration.** O downgrade **falha** se existir revisão > 1. Ele não apaga
  dado financeiro auditado, e voltar exige decisão humana.
- **Botão para perfil sem permissão.** O frontend ainda não conhece o perfil do usuário,
  então um usuário só de leitura vê o botão "Recalcular" e recebe a mensagem de falta de
  permissão. É a mesma limitação da importação de faturas.
- **Meses sem produção do inversor** continuam indisponíveis até a telemetria do período
  existir. O recálculo diz isso e não grava nada.
- **PDF/XLSX** usam o relatório mais recente da fatura mais recente, que é a revisão mais
  nova.

## Adendo (2026-10-23) — completar uma fatura confirmada pelo PDF

O recálculo em produção mostrou que mai, jun e jul/2026 continuam indisponíveis por
`TARIFF_NOT_AVAILABLE`. Essas faturas entraram pelo texto do Telegram antes de o leitor
saber ler a tarifa.

Reimportar o PDF criava um problema: o leitor não achava o mesmo texto, tentava criar outra
fatura do mesmo ciclo e esbarrava na unicidade, o que dava erro 500. Se as datas
divergissem, poderia até nascer uma segunda fatura do mês.

**Decisão:** em `POST /billing/intake-pdf`, quando já existe uma fatura **confirmada** da
mesma usina, distribuidora e mês, o PDF **só completa campos vazios**: tarifas, Fio B e
registro de geração. Para isso, tudo o que já existe tem de bater exatamente:

- datas do ciclo;
- consumo;
- saldo de créditos;
- valor total;
- campos já preenchidos.

Qualquer divergência dá 409, com uma mensagem fixa, e nada é alterado. Nunca se cria uma
segunda fatura do mês.

A operação é auditada como `billing.complete_from_pdf`, com os nomes dos campos preenchidos.
Depois dela, o mês aparece em "Meses a recalcular" e o recálculo gera a nova revisão.
