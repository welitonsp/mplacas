# ADR-078 — Injeção real pelo medidor e "conta com e sem a usina" (versão de cálculo 0.3.0)

## Status

**Aceito — 2026-10-15.** Fase 3 do plano de inteligência financeira (documento "MPlacas —
Inteligência do sistema: diagnóstico e plano"). Revisado pelo agente `reviewer`, que aprovou
com ressalvas; as ressalvas P1 foram tratadas antes do merge.

## Contexto

A conferência da fatura SCEE real da Equatorial Goiás de set/2026 mostrou o seguinte:

| Campo na fatura | Valor | O que o sistema fazia |
|---|---|---|
| Medidor, ENERGIA ATIVA | 221 kWh | `imported_kwh` (correto) |
| Medidor, ENERGIA GERAÇÃO | 235 kWh | `generation_cycle_kwh`, sem uso no cálculo |
| Linha "INJEÇÃO SCEE" | 221 kWh | `injected_kwh`, tratado como energia injetada na rede |
| "EXCEDENTE RECEBIDO" | 14 kWh | não lido |

A linha INJEÇÃO SCEE é a energia **compensada**: é igual ao consumo do ciclo. A energia que
saiu para a rede é o registro ENERGIA GERAÇÃO do medidor, e 235 − 221 = 14 kWh viraram
crédito. O ADR-050 tinha lido o registro do medidor como "geração bruta", mas na fatura real
ele é a exportação do medidor bidirecional.

Consequência: o autoconsumo era calculado como produção − 221 em vez de produção − 235. Isso
somava ao consumo, e portanto à economia do mês, 14 kWh que na verdade viraram crédito. Na
fatura de set/2026, são cerca de R$ 11 a mais por ciclo.

## Decisão

1. **A injeção na rede é o registro do medidor quando a fatura o traz.**
   `reconcile_bill` usa `generation_cycle_kwh` como injeção, e `injected_kwh` só quando o
   medidor não aparece (layouts antigos). `reconciliation.injected_kwh` passa a significar
   "energia que saiu para a rede". Novo campo: `excess_credit_kwh = max(0, injeção −
   compensado)`. Sem o medidor, ele vale `None`, nunca zero.
2. **"Conta com e sem a usina"**, calculada em `energy_engine` (padrão Arcadia/Genability:
   recalcular o mesmo período sem a geração própria e conferir o modelo contra a fatura real):
   - `bill_without_solar_brl` = consumo total × tarifa com impostos + iluminação pública.
     Vale a identidade `estimated_savings_brl` = `bill_without_solar_brl` − total pago, porque
     a fórmula da economia não mudou.
   - `credit_balance_value_brl` = saldo × (tarifa − Fio B). Um crédito usado ainda paga o
     Fio B (Lei 14.300). Sem o Fio B na fatura, usa a tarifa cheia como teto.
   - `modeled_bill_brl` = (importado − compensado usado) × tarifa + compensado usado × Fio B
     + iluminação, onde compensado usado = mín(compensado, importado). O resultado é `None`
     sem consumo importado no ciclo, para não fabricar diferença.
     `bill_model_difference_brl` é a sobra que o modelo não explica (custo mínimo de
     disponibilidade, retroativos, multas). A tela mostra essa sobra sem presumir a causa.
3. **A versão de cálculo sobe de 0.2.0 para 0.3.0.** Pelo ADR-038, os relatórios já emitidos
   continuam como estão, e os novos saem com a fórmula corrigida.

## Consequências

- **O ROI mistura versões.** `financial_return_service` soma `estimated_savings_brl` de todos
  os snapshots, inclusive os 0.2.0, cuja economia está inflada pelo excedente. O efeito é um
  viés para cima de cerca de R$ 11 por ciclo antigo com medidor. Isso foi aceito agora porque
  havia poucos ciclos confirmados em produção quando a mudança entrou. O painel do investidor
  (fase 4 do plano) vai expor quais versões compõem o acumulado e permitir recalcular um
  ciclo antigo sob a versão nova, sem apagar o snapshot original.
- **Telas diferentes, números diferentes para o mesmo mês.** O painel recalcula ao vivo
  (0.3.0), e o PDF/XLSX e o ROI leem o snapshot da época. A versão de cálculo já sai no
  relatório. Mostrar a versão na tela fica como pendência.
- **O mesmo nome com sentidos diferentes entre rotas.** Em `/billing/*`, `injected_kwh` é a
  linha da fatura (compensada). Em `/energy/*`, é a injeção real. A tela de conferência de
  faturas já rotula o campo pela origem. Renomear no contrato de `/billing` fica para uma
  mudança de contrato própria.
- **Inversor que subnotifica produz autoconsumo zero.** Com a injeção maior (235 em vez de
  221), fica mais provável a produção do inversor sair menor que a injeção (dias sem dado).
  Nesse caso o autoconsumo é zero, a economia sai subestimada, e não aparece aviso específico.
  O diagnóstico `MISSING_DAILY_DATA` cobre parte desses casos.
- **Fora do relatório mensal.** Os campos novos não entram no snapshot nem no PDF/XLSX,
  seguindo o mesmo critério do ADR-066 §4.

## Alternativas descartadas

- **Reescrever os snapshots 0.2.0.** Descartada porque viola o ADR-038 (imutabilidade).
- **Continuar usando a linha SCEE como injeção.** Descartada porque contradiz a fatura e
  infla a economia.
