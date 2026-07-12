# Fase P1 — Persistência histórica

## Objetivo

Garantir que o Mplacas mantenha histórico energético próprio, idempotente, versionado e independente da retenção da NEPViewer.

## Entregas

- SQLAlchemy assíncrono;
- PostgreSQL em produção e SQLite em desenvolvimento/testes;
- migrações Alembic;
- modelos de usina, dispositivo, produção diária e versões;
- armazenamento com `Decimal`;
- upsert idempotente por dispositivo e data;
- preservação do valor anterior em correções retroativas;
- coleta transacional NEPViewer → banco;
- rollback integral em falhas;
- readiness real do banco;
- política de coleta intradiária;
- consolidação D+1;
- backfill semanal dos sete dias encerrados;
- logs estruturados de início e conclusão;
- testes de persistência, idempotência e janelas temporais.

## Critérios de aceite

- executar a mesma coleta duas vezes não duplica dados;
- uma correção posterior gera uma versão histórica;
- o dia atual permanece provisório;
- o dia anterior é consolidado em D+1;
- o backfill não inclui o dia ainda aberto;
- uma falha durante a coleta não deixa gravações parciais;
- nenhum secret ou dado pessoal é persistido no repositório.

## Princípios

- nenhuma leitura ausente será convertida em zero;
- alterações da NEPViewer nunca sobrescrevem silenciosamente o histórico;
- energia usa `Decimal`, nunca `float`;
- timestamps são armazenados em UTC;
- a data de produção respeita o fuso da usina.

## Fora do escopo

- hospedagem do scheduler;
- bot Telegram;
- processamento da fatura Equatorial;
- conciliação financeira;
- dashboard público.
