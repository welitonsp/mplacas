# ADR-098 — Produção pela leitura do total da madrugada (Growatt sem histórico)

## Status

**Aceito — 2026-11-02.** Diagnóstico em produção (ADR-097, PRs #271/#272): o token Growatt
do cliente lê **só** `plant/list`. `plant/energy`, `plant/data`, `plant/details`,
`device/list` e `plant/power` voltam `10011 error_permission_denied`. É o mesmo relato de
outros projetos com tokens de conta final (Home Assistant e a biblioteca `growattServer`
só garantem leitura completa para inversores MIN e SPH). `plant/list` também é limitada
(`10012 error_frequently_access` quando repetida em pouco tempo).

## Decisão

1. **Tabela `meter_readings`** (`plant_id`, `device_id`, `reading_date`, `total_kwh`,
   `source`, `read_at`), única por aparelho e dia, com RLS forçado por usina (migração
   `20261102_0054`).
2. **Coleta diária** (`collection/job.py`): para `GROWATT_TOKEN`, quando o histórico é
   recusado **mas a lista respondeu**, o sistema lê o `total_energy` (kWh desde a instalação)
   da própria lista, já em cache no cliente, sem segunda chamada. Grava a leitura do dia e,
   havendo a da noite anterior, grava em `daily_energy` a diferença como produção de ontem
   (`CONSOLIDATED`, fonte `GROWATT_OPENAPI_V1`).
   - Só vale de **madrugada** (antes das 05:00 no fuso da usina): o total cobre a véspera
     inteira. A coleta roda às 03:07. Leitura de dia é descartada sem erro.
   - **Nada é inventado**: sem a noite anterior (primeira leitura ou noite perdida), o dia
     fica sem dado. Total menor que o anterior (troca de inversor, zeramento) não vira
     produção, e total **igual** também não: a lista da Growatt atualiza com atraso, e um dia
     de 0 kWh "confirmado" dispararia alerta falso.
   - Leitura de dia (execução manual fora de hora) conta como **adiada**, nunca como
     sucesso, e usa sempre a data local da leitura, não o `target_date` pedido.
   - Token recusado já na lista continua sendo falha de autenticação (fila e aviso na
     conexão), como antes.
3. **Importar histórico** (ADR-097): nesse caso a resposta é 200 com
   `history_available: false`, não erro. O Início explica que a produção passa a ser lida
   toda madrugada e não oferece "tentar de novo".
4. O teste de leitura de diagnóstico (PRs #271/#272) sai da importação. Fica o log
   `growatt_openapi_error` (endpoint, código e mensagem curta da Growatt).

## Consequências

- O cliente passa a ter produção diária real, com um dia de atraso, e nunca os 90 dias
  anteriores: a Growatt não os libera para esse token.
- O primeiro dia aparece depois de duas madrugadas.
- `meter_readings` cresce uma linha por usina por dia e fica fora da retenção de séries por
  decisão consciente (volume desprezível).
- Se a Growatt liberar o histórico (instalador ou suporte), o caminho normal volta sozinho:
  o fallback só entra quando o histórico é recusado.
