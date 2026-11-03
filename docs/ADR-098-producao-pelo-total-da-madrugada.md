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

## Revisão — 2026-11-03: a agenda do GitHub não cai de madrugada

A primeira versão contava com a coleta diária "às 03:07". Na prática o GitHub tem rodado a
agenda das 06:07 entre **12h e 17h**, ou seja, de dia, e a leitura nunca seria gravada.
Mudou para:

1. **Dia fechado em vez de madrugada.** O total lido depois das 19:30 ou antes das 05:00
   (escuro o ano todo em Goiás) fecha um dia: às 21:00 de D fecha D, e às 03:00 de D+1 também
   fecha D (`collection/meter.py: covered_date`). `meter_readings.reading_date` passa a
   significar **o dia fechado**, e a produção de D é `total(D) − total(D−1)`, gravada em D.
2. **Workflow próprio `meter-readings`**, a cada 6 h o dia todo, às 04:47, 10:47, 16:47 e 22:47 (o mínimo da política de
   custo zero). Como a janela escura tem 9 h 30, alguma execução cai nela qualquer que seja
   o atraso do GitHub. De dia o passo de checagem encerra antes de instalar qualquer coisa: não toca no
   banco (Neon dorme) nem na Growatt. No escuro faz uma `plant/list` por conexão Growatt por
   token de cliente ativo. Várias leituras na mesma noite ficam com a maior.
3. **Fonte própria `GROWATT_TOTAL_DIFF`** em `daily_energy`: a produção derivada nunca
   sobrescreve a que vier do histórico da marca.
4. **Coleta diária de dia**, com o histórico recusado e a lista ok, não é falha da conexão: a
   produção dessa conta vem do `meter-readings`. Se cair no escuro, já aproveita para ler.
5. **Falha alta**: o job tenta todas as usinas e termina com erro (workflow vermelho e e-mail
   do GitHub) se alguma falhar, porque uma leitura perdida custa dois dias de produção.
6. **Só a usina da conexão**: se o token enxergar outras usinas, entra só o total das que já
   estão ligadas a esta usina.
