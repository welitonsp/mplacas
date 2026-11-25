# ADR-101 — Descontinuação da integração Growatt

## Status

**Aceito — 2026-11-25.** Substitui os ADR-092, ADR-094, ADR-098 e ADR-099. Ajusta o
ADR-100 (a "família" de marcas passa a ser uma só).

## Contexto

O dono do produto não tem acesso à API oficial da Growatt. Sem ela, a integração depende
de token de conta final com permissão restrita (só `plant/list`, ver ADR-098) ou do login
clássico do app (ADR-092), ambos frágeis e fora do contrato do fabricante. A NEPViewer
(ADR-091) continua sendo a integração de referência.

## Decisão

1. A integração Growatt está **descontinuada**. A NEPViewer permanece.
2. **~~Mantido~~ — substituído pela seção "Exclusão definitiva" (25/11/2026) para as usinas conectadas pela Growatt:** faturas dos clientes, relatórios mensais, produção já coletada,
   aparelhos (`devices`), a tabela `meter_readings` (congelada, sem novas escritas
   depois do desligamento), e `provider_plant_claims` (a ser generalizada para uma
   marca só).
3. **Sequência segura:**
   1. recusar conexão nova (`CONNECTABLE_PROVIDERS`; este PR): 422 `provider_unsupported`
      em PUT, `/connect`, `/connect/preview` e `/connect/confirm`; `import-history` e
      `refresh-profile` de conexão existente: 409 `provider_discontinued`;
   2. aviso de "conexão desativada" na tela;
   3. comando de operador `discontinue-provider` (dry-run por padrão): desativa as conexões
      existentes e apaga a credencial guardada. Só aí a coleta agendada, a leitura da
      madrugada e a leitura ao vivo param;
   4. remover os jobs e o código da Growatt.
   Até o passo 3, a coleta agendada, o `meter-readings` e
   `GET /plants/{id}/provider-account/now` continuam funcionando para as conexões
   existentes (`SUPPORTED_PROVIDERS` e `build_client` não mudam neste PR). O operador pode
   desativar o workflow `meter-readings` no GitHub a qualquer momento.
4. **Nunca fazer:** apagar `devices` isoladamente (a exclusão em cascata leva a produção
   junto); apagar ou reescrever produção com origem Growatt fora do comando abaixo; apagar
   linhas de `provider_accounts` isoladamente (desativar e limpar a credencial, sem remover
   a linha); remover `meter_readings` sem backup. **A exclusão de usinas só acontece pelo
   comando `purge-discontinued-plants`** (seção abaixo) — nunca por migração, nunca por SQL
   avulso.

## Consequências

### Positivas

Sem credencial de terceiros sem uso guardada, sem chamadas a uma API sem contrato, menos
código a manter. ~~Histórico dos clientes preservado.~~ (Substituído: as usinas Growatt, com
faturas e relatórios, são apagadas pelo comando de exclusão definitiva.)

### Negativas

~~Clientes Growatt perdem a coleta nova a partir do passo 3 e ficam só com o histórico.~~ (Substituído: perdem a usina inteira.)
Há um intervalo entre os passos 1 e 3 em que a conexão existe, mas não aceita
reimportação nem releitura do cadastro.

## Validação

Testes de recusa em `tests/test_provider_growatt_descontinuada.py`; a suíte existente da
NEPViewer segue passando.

## Reversibilidade

Até o passo 3, basta voltar `CONNECTABLE_PROVIDERS` a incluir as marcas Growatt. Depois
do passo 3 as credenciais foram apagadas e os clientes precisariam reconectar. **Depois do
comando de exclusão definitiva, a única volta é restaurar o backup** feito antes dele.

## Exclusão definitiva (decisão do dono, 25/11/2026)

O dono escolheu, depois de avisado de que é irreversível, **apagar por inteiro as usinas
conectadas pela Growatt**, inclusive as faturas confirmadas e os relatórios mensais, depois
de um backup do banco feito imediatamente antes. Isto prevalece sobre a regra anterior de
preservar o histórico. As usinas da NEPViewer não são tocadas.

Única via: `python -m mplacas.cloud_jobs purge-discontinued-plants [--apply]
[--confirm-plant-count N] [--totals-only]` (workflow manual `purge-discontinued-plants`,
que só aplica com `confirmacao` = `EXCLUIR`).

- **Seleção:** usina com conexão (ativa ou não) de marca descontinuada, com aparelho
  `GROWATT*` ou com produção de origem `GROWATT*`. Se alguma selecionada também tiver
  conexão, reserva ou aparelho de outra marca, a execução inteira é recusada.
- **Simulação por padrão:** só contagens agregadas por categoria. `--apply` exige
  `--confirm-plant-count` igual ao número selecionado.
- **Uma transação**, contexto de plataforma. Ordem: `daily_energy_versions`, `daily_energy`,
  `meter_readings`, `monthly_report_snapshots`, `report_export_tasks`, `utility_bills`,
  `collection_tasks`, `outbox_events`, `alert_delivery_records`,
  `daily_climate_observations`, as quatro tabelas de resultados fotovoltaicos,
  `pipeline_executions`, `provider_plant_claims`, `provider_accounts` (a credencial cifrada
  some com a linha), `devices`, `plants`. Antes, `organizations.default_plant_id` vira NULL e
  a usina sai de `api_credentials.plant_ids`. Depois, confere que nada das usinas restou e
  que nada do resto mudou; qualquer divergência desfaz a transação.
- **Usuários e organizações** não são apagados. Dois ajustes de referência: a usina padrão
  da organização vira NULL e a usina sai de `api_credentials.plant_ids`; a credencial cujo
  escopo ficaria vazio é **revogada** (`active=false`, `revoked_at`, `plant_ids=[]`; nunca
  NULL, que significaria a organização inteira). Uma lista vazia é lida como escopo que não
  permite nada (`PlantScope.empty()`), nunca como erro.
- **Auditoria da usina também é apagada** (o dono escolheu apagar a usina inteira): os
  `audit_events` com `resource_type` `plant` (id da usina), `utility_bill` (id das faturas
  apagadas) ou `pipeline_execution` (id das execuções apagadas), mais qualquer evento cujo
  texto de `details` (qualquer chave, inclusive aninhada) contenha o UUID completo de uma das
  usinas (ex.: `plant.created_from_connection`). Os demais
  tipos (`organization`, `api_credential`, `user_invitation`, `operational_user`) ficam.
  Sobra apenas o evento de plataforma `plant.purged_discontinued_provider`, com contagens
  (`{"plants": N, "reason": "provider_discontinued", "adr": "ADR-101"}`).
- **Concorrência:** na PostgreSQL as linhas das usinas são travadas (`FOR UPDATE`) e a recusa
  é reavaliada depois da trava. Rode fora do horário dos jobs agendados (coleta, leitura da
  madrugada, pipeline diário). Um rollback por divergência na verificação é seguro e basta
  repetir o comando. A verificação da auditoria é por id (os eventos levantados sumiram e
  há exatamente um evento de plataforma novo), não pelo total da tabela, que muda com
  qualquer requisição da API; as demais tabelas são conferidas por contagem global, porque
  só os jobs escrevem nelas. Se a seleção mudar entre a primeira leitura e a trava, o comando
  recusa e desfaz.
- Com 0 usinas selecionadas o `--apply` é um no-op com código 0 (a confirmação não é
  comparada), para a reexecução do workflow não falhar.
- Idempotente: a segunda execução seleciona 0 e não muda nada. O log público só mostra
  contagens e nomes de classe de exceção.
