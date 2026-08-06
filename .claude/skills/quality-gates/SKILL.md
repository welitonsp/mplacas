---
name: quality-gates
description: Use antes de considerar qualquer fase/tarefa concluída no Mplacas — checklist de lint, typecheck, testes, build, acessibilidade, bundle, segredo, rotas e critério de aceite. Base para o agente quality-gate-reviewer e reviewer.
---

# Quality Gates — Mplacas

## Finalidade
Definir exatamente o que "pronto" significa, sem depender de aparência.

## Checklist obrigatório
- **Backend**: `ruff check .`, `mypy src`, `pytest -q` (suíte inteira) — todos limpos.
- **Frontend**: `npm run type-check`, `npm run test` (suíte inteira), `npm run build` — todos limpos.
- **Bundle**: delta gzip reportado quando a mudança toca frontend (ver `frontend-performance`).
- **Acessibilidade**: guard de contraste e ARIA não regrediram (ver `wcag-aa`/`accessibility-testing`).
- **Segredo**: nenhuma credencial nova em código, log ou `localStorage` sem allowlist justificada (ver `secret-safe-ui`).
- **Rotas/escopo de risco**: se a mudança toca organizations/auth/credentials/billing/migrations, reviewer é obrigatório (regra do CLAUDE.md do projeto).
- **Critério de aceite**: a tarefa original tinha um critério verificável explícito — confirme que ele foi de fato atendido, não só que "o código parece certo".
- **Regressão**: suíte completa rodada, não só os arquivos tocados.

## Procedimento
1. Rode os comandos você mesmo — não aceite o relato de quem implementou sem verificação independente quando o papel exigir isso (reviewer/quality-gate-reviewer).
2. Se qualquer item falhar, a fase não está concluída — devolva com o item específico que falta, não uma reprovação genérica.

## Anti-patterns
- Aprovar com base só em "os testes que eu escrevi passam" sem rodar a suíte inteira.
- Pular o gate porque "é uma mudança pequena".

## Checklist
- [ ] Todos os comandos de gate rodados e limpos
- [ ] Critério de aceite original verificado, não assumido
- [ ] Reviewer acionado quando a área de risco exigir
