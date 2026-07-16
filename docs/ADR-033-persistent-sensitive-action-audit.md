# ADR-033 - Auditoria persistente de ações sensíveis

## Status

Aceito.

## Contexto

As ADRs 031 e 032 criaram papéis operacionais e fingerprint seguro da credencial usada em cada
requisição. Ainda faltava persistir ações sensíveis de negócio para investigação posterior, mesmo
quando logs externos forem rotacionados.

O primeiro escopo deve ser pequeno e não invasivo: registrar confirmação/rejeição de faturas e
execuções de pipeline sem gravar payloads privados, texto de fatura, tokens, senhas, CPF, endereço ou
dados brutos de provedores.

## Decisão

1. Criar a tabela `audit_events`.
2. Registrar em cada evento:
   - ação;
   - tipo de recurso;
   - identificador do recurso;
   - resultado;
   - papel operacional;
   - fingerprint da credencial operacional;
   - `request_id`;
   - detalhes não sensíveis.
3. Criar índices por ação/data, recurso e ator.
4. Registrar eventos de sucesso para:
   - `billing.confirm`;
   - `billing.reject`;
   - `pipeline.run`.
5. Registrar evento de falha para `pipeline.run` quando a execução chega ao runtime e retorna erro
   operacional.
6. Não registrar texto bruto de fatura, payload externo, token, senha, chave operacional, CPF ou
   endereço.

## Consequências

### Positivas

- Ações críticas passam a ter trilha persistente no banco.
- A investigação pode correlacionar `request_id`, papel e fingerprint da credencial.
- O modelo abre caminho para auditoria de usuário/tenant quando RBAC completo existir.

### Negativas

- A auditoria ainda identifica credenciais, não pessoas nominais.
- Eventos anteriores a esta migration não terão trilha retroativa.
- É necessário executar a migration antes da próxima versão de produção.

## Validação

A entrega deve permanecer coberta por:

- teste do repositório de auditoria;
- teste de contrato da migration;
- teste do endpoint de pipeline verificando solicitação de evento;
- Ruff;
- Mypy;
- Pytest.

