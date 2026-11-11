# ADR-100 — Reserva da usina do fabricante na conexão

## Status

**Aceito — 2026-11-11.** Fecha a lacuna em que duas organizações conectam a mesma usina
Growatt antes da primeira coleta. Depende da migration `20261111_0055` (tabela
`provider_plant_claims`), que precisa estar aplicada antes do deploy deste código.

## Contexto

Uma usina física do fabricante só pode estar ligada a uma usina do Mplacas (ADR-091). Duas
barreiras existiam e nenhuma cobria o intervalo entre a conexão e a primeira coleta:

- **Impressão digital da conta** (`account_fingerprint`): não pega o token Growatt, porque o
  login dele é aleatório por requisição (`_token_login`) e o ADR-094 proíbe fazer hash do
  token. Também não liga uma conta por senha (`GROWATT`) a uma por token (`GROWATT_TOKEN`).
- **Aparelhos** (`_inverter_in_another_plant`, tabela `devices`): as linhas de `devices` só
  nascem na primeira coleta, nunca na conexão. Até lá, nada barra.

Resultado: duas organizações podiam conectar o mesmo token (ou senha em uma e token na
outra) e só descobrir o conflito na coleta, quando a segunda falhava. A lacuna estava
documentada em `tests/test_growatt_token_cross_org.py` (seis testes `xfail(strict=True)`).

## Decisão

1. **Tabela `provider_plant_claims`** (`ProviderPlantClaimRecord`), uma linha por usina física
   reservada, com `UNIQUE(provider_family, serial_number)`. O índice único do PostgreSQL vale
   também para linhas que o RLS esconde do inquilino que insere: o INSERT da organização B
   falha contra a reserva invisível da A. Isso fecha a corrida entre duas conexões simultâneas.
2. **Família da marca** (`provider_family`): `GROWATT` para `GROWATT` e `GROWATT_TOKEN`; o
   próprio nome nas demais. A conferência dos aparelhos no roteador usa a mesma noção.
3. **Um único ponto de gravação**: `ProviderAccountService.save(..., serials=...)`, argumento
   obrigatório. Na mesma transação, depois da conferência da impressão digital e da gravação
   da conta, apaga as reservas da usina e grava uma por série distinta, num `begin_nested()`
   próprio. Um `IntegrityError` ali vira `ProviderPlantClaimConflictError` (subclasse de
   `ProviderAccountConflictError`), distinguível do conflito da impressão digital. O texto do
   erro do banco traz o número de série e nunca entra em exceção, log, auditoria ou resposta.
4. **Liberação**: `deactivate` apaga as reservas da usina na mesma transação.
5. **Rotas** (`PUT provider-account`, `POST /plants/connect`, `POST /plants/connect/confirm`):
   passam as séries inspecionadas e respondem 409 `provider_inverter_in_another_plant` (com
   recusa auditada e `rollback`, sem deixar `Plant`) quando a reserva conflita.
   `_inverter_in_another_plant` também consulta as reservas, para recusar cedo (antes da
   geocodificação e da prévia); a restrição UNIQUE continua sendo a barreira real.

Decisões do responsável:

- Uma conexão reserva **todas** as séries que a inspeção devolveu (token que enxerga várias
  usinas reserva todas).
- Desconectar libera as reservas, mas a usina que já tem `Device` coletado continua barrando
  as outras pela conferência de `devices`, sem mudança.

### Alternativas descartadas

- **Criar `Device` na conexão.** A leitura "agora" somaria usinas de vizinhos em tokens com
  várias usinas, não haveria como liberar ao desconectar, e senha contra token continuaria
  descoberto no banco.
- **Impressão digital derivada do id da usina na marca.** Não cruza senha e token, e o
  ADR-094 proíbe fazer hash do token.

## Consequências

### Positivas

- A segunda organização é recusada na conexão, não na coleta, inclusive em corrida.
- Senha em uma organização e token na outra passam a se barrar.

### Negativas

- Conexões existentes não têm reserva até o passo de backfill; até lá só os aparelhos já
  coletados as protegem.
- Duplicatas legadas (já conectadas nas duas organizações) são apenas reportadas, nunca
  removidas automaticamente.
- O token de um instalador que enxerga várias usinas passa a bloquear os clientes dele mais
  cedo que antes.
- Reconectar a mesma usina com outro token substitui as reservas dela; a série antiga fica
  livre para outras organizações.

### Fora do escopo

A coleta diária, o job da madrugada, a importação de histórico e a leitura "agora" continuam
tratando tudo que o token enxerga; limitá-las às séries reservadas é decisão separada.

## Validação

`tests/test_growatt_token_cross_org.py` (corrida com a conferência antecipada desligada,
liberação ao desconectar, substituição na reconexão, família senha/token, outra marca com a
mesma série, ausência de vazamento), `tests/test_provider_accounts.py` (serviço) e, em
PostgreSQL, `tests/test_postgres_application_rls.py`.

## Reversibilidade

Remover o argumento `serials` e as chamadas às reservas devolve o comportamento anterior; a
tabela pode ficar vazia sem efeito.
