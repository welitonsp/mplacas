# ADR-034 - Auditoria persistente ampliada para mutacoes administrativas

## Status

Aceito.

## Contexto

A ADR-033 introduziu a tabela `audit_events` e registrou as primeiras acoes sensiveis:
confirmacao/rejeicao de faturas e execucao do pipeline operacional. A auditoria tecnica ainda
mantinha uma pendencia aberta: ampliar a trilha persistente para outras mutacoes administrativas que
alteram estado de negocio ou disparam efeitos externos.

Os endpoints restantes de maior impacto eram:

- `POST /billing/intake-text`, que cria faturas pendentes;
- `POST /climate/collect`, que persiste observacoes climaticas;
- `POST /alerts/run`, que avalia, envia e deduplica alertas.

## Decisao

1. Registrar eventos de sucesso para:
   - `billing.intake_text`;
   - `climate.collect`;
   - `alerts.run`.
2. Usar os mesmos campos da ADR-033: acao, recurso, identificador do recurso, resultado, ator
   operacional, fingerprint da credencial, `request_id` e detalhes sanitizados.
3. Manter detalhes restritos a IDs, datas, status e contadores operacionais.
4. Nao gravar texto bruto de fatura, token do Telegram, chat id bruto, payload externo, chave
   operacional, CPF, endereco ou resposta integral de provedor.
5. Registrar apenas mutacoes efetivamente aceitas nesta fase; rejeicoes de validacao continuam
   retornando erro sem persistir payload sensivel.

## Consequencias

### Positivas

- A criacao de faturas pendentes passa a ser rastreavel antes da revisao humana.
- Coletas climaticas operacionais ficam correlacionaveis por usina, periodo, provedor e contadores
  de persistencia.
- Execucoes manuais de alerta passam a deixar trilha de resultado sem expor destino privado.
- A cobertura prepara a migracao futura para usuarios, tenants e escopos por `plant_id`.

### Negativas

- A auditoria ainda identifica credenciais operacionais, nao usuarios nominais.
- Eventos anteriores a esta entrega permanecem sem retroatividade.
- Falhas rejeitadas antes da mutacao nao ficam no ledger persistente para evitar capturar contexto
  sensivel desnecessario.

## Validacao

A entrega deve permanecer coberta por:

- testes dos endpoints de fatura, clima e alertas verificando evento de auditoria sanitizado;
- teste existente do repositorio de auditoria;
- teste de contrato da migration `audit_events`;
- Ruff;
- Mypy;
- Pytest.
