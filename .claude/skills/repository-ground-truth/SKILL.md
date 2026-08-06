---
name: repository-ground-truth
description: Use antes de qualquer diagnóstico ou auditoria do repositório Mplacas — obriga a confirmar branch/commit/status real e produzir evidência com arquivo:linha antes de qualquer conclusão. Use sempre que for avaliar "o que existe hoje" no código.
---

# Repository Ground Truth

## Finalidade
Impedir que diagnósticos partam de suposição, relatório externo desatualizado ou "achismo". Toda afirmação sobre o estado do repositório precisa de evidência rastreável.

## Quando usar
- Antes de qualquer auditoria de UI/UX, arquitetura ou segurança.
- Quando um documento externo (prompt do usuário, relatório de terceiro) descreve o estado do projeto — verificar antes de aceitar.
- Como primeiro passo de qualquer tarefa do `repo-auditor`.

## Quando não usar
- Para decidir o que implementar (isso é `frontend-architecture`/`product-uiux-lead`).
- Para revisar um diff já escrito nesta sessão (isso é `quality-gates`/`secure-code-review`).

## Entradas necessárias
- Acesso de leitura ao repositório (`Read`, `Grep`, `Glob`, `Bash` git).

## Procedimento
1. `git status --short`, `git log --oneline -1`, `git branch --show-current` — registre os três antes de qualquer outra coisa.
2. Para rotas: leia `frontend/src/App.tsx` (frontend) e os `router.py` relevantes (backend) — nunca infira rota de nome de arquivo.
3. Para componentes/páginas: `Glob` em `frontend/src/pages/**` e `frontend/src/components/**`, depois `Read` os que forem relevantes à pergunta.
4. Para testes: `Glob` `**/*.test.tsx` / `tests/test_*.py` na área em questão — confirme que existe e o que ele afirma, não assuma cobertura.
5. Para tokens/design: leia `frontend/src/index.css` diretamente, não confie em memória de sessões anteriores (pode ter mudado).
6. Monte a matriz final: afirmação → evidência (arquivo:linha) → confiança (confirmado no código / confirmado em execução / inferido / não verificado).

## Critérios de saída
- Toda afirmação relevante tem `arquivo:linha` associado.
- Nenhuma afirmação usa linguagem absoluta ("não existe X") sem `Grep`/`Glob` que comprove a ausência.
- Divergências entre documento externo e código real estão listadas explicitamente, não silenciadas.

## Anti-patterns
- Aceitar a nota/conclusão de uma auditoria externa sem reverificar contra o código.
- Dizer "provavelmente" sem tentar confirmar primeiro.
- Confundir "não encontrei em 2 greps" com "não existe" — busque por sinônimos antes de concluir ausência.

## Checklist
- [ ] Branch/commit/status registrados
- [ ] Toda afirmação tem evidência de arquivo
- [ ] Divergências com documentos externos listadas
- [ ] Nada foi modificado (esta skill é read-only)
