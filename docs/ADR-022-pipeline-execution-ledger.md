# ADR-022 — Controle persistente das execuções do pipeline

## Status

Proposto.

## Contexto

A PR nº 25 criou a orquestração diária de coleta climática, análise energética e alertas. Faltava impedir duas execuções concorrentes para a mesma usina e data, registrar tentativas e permitir auditoria de sucesso ou falha.

## Decisão

1. Cada execução é identificada pela chave lógica `plant_id + target_date`.
2. A tabela `pipeline_executions` mantém um único registro por chave lógica.
3. Os estados permitidos são `RUNNING`, `SUCCEEDED` e `FAILED`.
4. Uma execução em `RUNNING` bloqueia nova aquisição para a mesma usina e data.
5. Execuções concluídas ou falhas podem ser reutilizadas como nova tentativa, incrementando `attempt_count`.
6. O estágio atual é persistido em campo sanitizado e limitado.
7. Falhas armazenam somente um código técnico, nunca mensagens externas, credenciais ou payloads.
8. A migração `20260713_0007` cria a tabela, índices e restrição de unicidade.
9. O serviço operacional continuará responsável pela fronteira final de transação.

## Consequências

- concorrência duplicada passa a ser rejeitada explicitamente;
- reexecuções ficam auditáveis;
- falhas podem ser retomadas sem criar registros duplicados;
- uma etapa posterior poderá adicionar endpoint protegido, duração por etapa e recuperação de locks abandonados.

## Segurança

Nenhuma coordenada, token, destino do Telegram, conteúdo de fatura ou resposta de provedor é persistido. O ledger contém somente identificadores técnicos, datas, estados, contadores e códigos de erro sanitizados.
