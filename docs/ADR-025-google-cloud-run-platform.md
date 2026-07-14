# ADR-025 — Google Cloud Run como plataforma de execução

## Status

Aceito.

## Contexto

O Mplacas precisa de uma plataforma de baixo custo para API, dashboard e tarefas
operacionais. A aplicação já é FastAPI stateless, usa PostgreSQL via SQLAlchemy async,
possui pipeline operacional idempotente e endpoints `/health` e `/ready`.

## Decisão

1. Executar API e dashboard em Google Cloud Run.
2. Executar migrações e pipeline diário por Cloud Run Jobs.
3. Acionar jobs recorrentes por Cloud Scheduler com IAM.
4. Usar Neon PostgreSQL como PostgreSQL gerenciado, sem acoplamento de domínio a Neon.
5. Usar Secret Manager para segredos.
6. Manter contêiner stateless, sem migração ou scheduler no startup.
7. Usar `PORT` do Cloud Run com fallback local 8080.
8. Manter escala a zero e limite inicial de uma instância.

## Alternativas

- VM em Compute Engine: mais controle, maior responsabilidade operacional e risco de custo.
- Cloud SQL: integração forte no Google Cloud, porém fora da meta inicial de custo.
- Serviço sempre ativo: reduz cold start, mas contraria a meta de Free Tier.
- Scheduler chamando endpoint público: simples, mas pior para segurança administrativa.

## Consequências

- O serviço web permanece stateless e escalável.
- Jobs operacionais têm exit code próprio e logs separados.
- Migrações ficam explícitas e fora do startup HTTP.
- O banco continua sendo PostgreSQL padrão.
- A implantação real exige configuração IAM e Secret Manager na etapa operacional.

## Riscos e limites

- Cold starts podem ocorrer com escala a zero.
- Neon Free pode pausar ou limitar conexões conforme plano.
- Scheduler, logs e Artifact Registry podem gerar custo se mal configurados.
- A aplicação não declara SLA nem disponibilidade 24/7 nesta decisão.

## Segurança

Segredos entram por Secret Manager ou variáveis do ambiente de execução, nunca por ARG ou
ENV fixo no Dockerfile. A imagem roda com usuário não root e não inclui `.git`, `.env`,
testes, documentação, PDFs, dumps ou banco SQLite local.
