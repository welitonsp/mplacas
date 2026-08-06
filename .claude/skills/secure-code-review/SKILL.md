---
name: secure-code-review
description: Use ao revisar um diff no Mplacas por segurança — isolamento multi-tenant, segredo exposto, autorização, injeção. Foco especial em qualquer mudança que toque organizations/auth/credentials/billing/migrations (reviewer obrigatório por regra do CLAUDE.md do projeto).
---

# Secure Code Review — Mplacas

## Finalidade
Checklist de segurança para revisão independente de diff, com foco no que já causou incidente real no histórico do projeto (isolamento entre organizações).

## Checklist
- **Isolamento multi-tenant**: toda query nova que toca dado de organização/usina respeita `set_principal_context`/RLS; nenhum dado de uma organização pode vazar para outra, mesmo em cenário de dado corrompido (ex: FK apontando para registro de outra organização — ver histórico do ADR-069 E2).
- **Autorização**: toda rota nova resolve escopo via `ReadPlant`/`AdminPlant`/`ScopedPlant`/`AdminPrincipal` (ou está na allowlist documentada de `test_plant_scope_guard.py` com motivo real).
- **Segredo**: nenhuma credencial hardcoded, logada, ou exposta em resposta de API/URL.
- **Injeção**: nenhuma query SQL montada por concatenação de string; toda entrada de usuário validada/tipada (Pydantic no backend).
- **404 vs 403 vs 409**: recurso de outro tenant retorna 404 (não revela existência), nunca 403/409 que vazaria informação.
- **Falha fechada**: erro/exceção não tratada nunca deve resultar em acesso concedido por omissão.

## Procedimento
1. Rode os testes de fronteira de tenant relevantes você mesmo (`tests/test_*_tenant_boundaries.py`), não confie no relato de quem implementou.
2. Para qualquer nova query cruzando tabelas sob RLS, confirme se há teste `postgres_integration` cobrindo (SQLite não aplica RLS de verdade).
3. Classifique achado como bloqueante sempre que envolver vazamento real ou potencial entre organizações.

## Anti-patterns
- Aprovar mudança em `organizations`/`billing`/`credentials` sem rodar teste de isolamento você mesmo.
- Aceitar 403/409 para recurso de outro tenant em vez de 404.

## Checklist
- [ ] Isolamento multi-tenant verificado com teste real, não assumido
- [ ] Autorização de rota nova confirmada (dependência correta ou allowlist justificada)
- [ ] Nenhum segredo exposto
- [ ] Falha fechada, não aberta
