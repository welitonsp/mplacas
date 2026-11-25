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
2. **Mantido:** faturas dos clientes, relatórios mensais, produção já coletada,
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
4. **Nunca fazer:** apagar `devices` (a exclusão em cascata leva a produção junto);
   apagar usinas; apagar ou reescrever produção com origem Growatt; apagar linhas de
   `provider_accounts` (desativar e limpar a credencial, sem remover a linha); remover
   `meter_readings` sem backup.

## Consequências

### Positivas

Sem credencial de terceiros sem uso guardada, sem chamadas a uma API sem contrato, menos
código a manter. Histórico dos clientes preservado.

### Negativas

Clientes Growatt perdem a coleta nova a partir do passo 3 e ficam só com o histórico.
Há um intervalo entre os passos 1 e 3 em que a conexão existe, mas não aceita
reimportação nem releitura do cadastro.

## Validação

Testes de recusa em `tests/test_provider_growatt_descontinuada.py`; a suíte existente da
NEPViewer segue passando.

## Reversibilidade

Até o passo 3, basta voltar `CONNECTABLE_PROVIDERS` a incluir as marcas Growatt. Depois
do passo 3 as credenciais foram apagadas e os clientes precisariam reconectar.
