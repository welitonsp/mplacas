# ADR-036 - Fronteira de leitura de faturas confirmadas

## Status

Aceito.

## Contexto

Os servicos de inteligencia consultavam `UtilityBillRecord` e `BillStatus` diretamente. A consulta
de faturas confirmadas, a ordenacao do ciclo mais recente e a conversao do registro SQLAlchemy para
`UtilityBill` estavam distribuidas entre ciclo, historico e dashboard executivo. Isso acoplava o
dominio de inteligencia ao schema de persistencia de billing e permitia divergencia futura entre as
consultas.

## Decisao

1. Criar `ConfirmedBillReadRepository` como unica fronteira de leitura de faturas confirmadas.
2. Expor `ConfirmedBill`, modelo imutavel que contem somente identidade, escopo de usina e a fatura
   de dominio `UtilityBill`.
3. Manter na fronteira de billing as regras de status confirmado, escopo obrigatorio por
   `plant_id`, ordenacao por fim do ciclo e conversao de persistencia para dominio.
4. Fazer ciclo, historico e dashboard executivo consumirem `ConfirmedBill`, sem importar
   `billing.db_models`.
5. Preservar contratos HTTP, mensagens de erro, formulas, ordenacao e schema do banco.
6. Nao introduzir nesta fase um agregado `BillingCycle`, snapshot materializado, cache ou nova
   autorizacao. Essas decisoes exigem invariantes e ciclos de vida proprios.

## Consequencias

### Positivas

- A inteligencia deixa de conhecer tabelas e enums de persistencia de billing.
- A semantica de fatura confirmada e mais recente passa a ser testada em um unico lugar.
- Faturas pre-carregadas podem ser analisadas sem nova consulta ao registro de billing.
- A fronteira prepara o sistema para escopo de autorizacao por usina e snapshots versionados.

### Negativas

- Existe mais um contrato interno e uma conversao explicita entre persistencia e dominio.
- O repositorio de escrita permanece separado do repositorio de leitura e ambos precisam evoluir de
  forma coordenada quando o schema de faturas mudar.

## Validacao

A entrega deve permanecer coberta por:

- testes de leitura por identificador e escopo de usina;
- testes de ordenacao das duas faturas confirmadas mais recentes;
- teste de fronteira que impede importacao de `billing.db_models` por `intelligence`;
- testes existentes de ciclo, historico, dashboard, relatorios e endpoints;
- Ruff;
- Mypy;
- Pytest.
