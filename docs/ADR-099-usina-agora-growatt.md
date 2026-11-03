# ADR-099 — "Sua usina agora" para contas Growatt sem histórico

## Status

**Aceito — 2026-11-03.** O cliente com token Growatt restrito (ADR-098) só ganha produção
diária depois de duas noites de leitura. Até lá, e depois também, a lista de usinas já
informa o **total gerado desde a instalação** e a **potência no momento**.

## Decisão

1. **`GET /plants/{id}/provider-account/now`** (qualquer usuário com leitura da usina): só para
   conexões `GROWATT_TOKEN`. Outras marcas recebem 404 `plant_now_unavailable`. Lê
   `plant/list` com a conexão guardada e devolve `total_kwh`, `current_power_kw` e `read_at`.
   A resposta nunca traz login nem token.
2. **Cache em memória de 10 minutos por usina**: a Growatt recusa `plant/list` repetida em
   pouco tempo (10012). Se a marca falhar ou limitar e houver leitura em cache, devolve a
   última leitura em vez de erro. A instância é única no Render; um cold start só refaz
   a leitura.
3. **Só a usina da conexão**: se o token enxergar outras usinas, entram só os aparelhos já
   ligados a esta usina.
4. **Campo ausente ou ilegível vira `null`, nunca zero.** A tela mostra "não informado".
5. **Início**: cartão "Sua usina agora", com "Gerando agora" (kW), "Total desde a instalação"
   (kWh), selo "Medido" e "Lido na Growatt às HH:MM". Qualquer falha só esconde o cartão.

## Consequências

- O cliente vê a usina funcionando no mesmo dia em que conecta.
- O total exibido não é recalculado pelo sistema. É o número da Growatt, com a fonte visível.
