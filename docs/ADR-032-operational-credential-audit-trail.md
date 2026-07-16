# ADR-032 - Trilha auditável de credencial operacional

## Status

Aceito.

## Contexto

A ADR-031 introduziu papéis operacionais `ADMIN` e `READ`, mas ainda faltava uma forma segura de
correlacionar uma requisição autenticada com a credencial usada. Como o sistema ainda não possui
usuários nominais, tenants ou claims por usina, a melhor trilha inicial é registrar um identificador
estável da credencial sem expor o segredo.

## Decisão

1. Cada `OperationsPrincipal` passa a carregar:
   - `role`;
   - `credential_id`.
2. `credential_id` é derivado de SHA-256 da chave configurada, truncado e prefixado pelo papel:
   - `operations:admin:<fingerprint>`;
   - `operations:read:<fingerprint>`.
3. A chave original nunca é registrada, retornada ou persistida.
4. As dependências de autenticação operacional gravam o principal em `request.state`.
5. O middleware HTTP inclui nos logs de requisição, quando existir autenticação operacional:
   - `operations_role`;
   - `operations_credential_id`.
6. O log continua sem payload, query string, token, senha ou valor bruto de chave.

## Consequências

### Positivas

- Permite correlacionar leituras e operações administrativas por credencial sem vazar segredo.
- Facilita investigação operacional junto com `X-Request-ID`.
- Prepara a migração futura para ator nominal, tenant e escopo por usina.

### Negativas

- O identificador ainda representa uma credencial, não uma pessoa.
- Rotação de chave muda o `credential_id`, exigindo correlação por janela temporal nos logs.
- Não substitui auditoria persistente de ações de negócio.

## Validação

A entrega deve permanecer coberta por:

- teste garantindo que o principal `ADMIN` gera `credential_id` sem conter a chave;
- teste garantindo que o principal `READ` gera `credential_id` sem conter a chave;
- teste garantindo que o log HTTP autenticado contém `operations_role` e
  `operations_credential_id`;
- Ruff;
- Mypy;
- Pytest.

