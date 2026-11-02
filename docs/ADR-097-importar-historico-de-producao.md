# ADR-097 — Importar o histórico de produção logo depois de conectar

## Status

**Aceito — 2026-11-02.** Teste real do dono: o cliente conectou a Growatt pelo assistente
(ADR-096), a usina nasceu com 4,5 kWp lidos da marca, mas o Início mostrou "Não foi possível
carregar os dados" e "Nenhuma leitura da usina nos últimos 90 dias". A coleta só rodava na
madrugada (06:07 UTC) e a usina ainda não tinha fatura.

## Decisão

1. **`POST /plants/{plant_id}/provider-account/import-history`** (ADMIN da usina): com a conexão
   guardada, busca na marca a produção dos **últimos 90 dias até ontem** (fuso de
   `settings.timezone`) e grava com o mesmo `SolarCollectionService` da coleta diária, então é
   idempotente — reimportar só atualiza os dias. Roda no contexto de plataforma, como a coleta
   diária, porque a checagem de inversor em outra usina precisa enxergar todas as organizações;
   a usina já foi autorizada antes (ADMIN da organização).
2. **Teto próprio**: 2 importações a cada 10 minutos por usina, contando sucesso
   (`provider_account.history_imported`) e falha (`provider_account.history_import_failed`).
   Esse teto é separado do da conexão: uma marca fora do ar não impede trocar a senha, e
   tentativas de senha não bloqueiam a importação.
3. **Erros** como na releitura do cadastro (ADR-094): senha/token recusados = 422, marca fora
   do ar ou bloqueando = 503, inversor em outra usina = 409, conexão ilegível = 503. A resposta
   nunca traz login, senha ou token; a auditoria guarda só a marca e as contagens.
4. **Início**:
   - sem leitura (histórico 404) e usuário ADMIN: o Início dispara a importação **uma vez por
     usina enquanto a aba estiver aberta**, mostra "Buscando na marca a produção dos últimos 90
     dias…" e recarrega ao terminar; um botão **Buscar produção na marca** permite tentar de
     novo. Quem só lê não dispara nada;
   - sem fatura (executivo 404): estado vazio "A economia aparece depois da primeira fatura",
     com link para Dinheiro — nunca mais "Erro ao buscar dados" para uma usina nova.

## Consequências

- A primeira impressão depois de conectar passa a ter produção real em segundos.
- Cada importação faz cerca de 13 chamadas à Growatt (janelas de 7 dias); o teto evita
  insistência que leve a marca a bloquear a conta.
- Sem migração: só auditoria nova.
