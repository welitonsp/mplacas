---
name: python-quality
description: Use SEMPRE que um arquivo .py do projeto Mplacas for criado ou modificado (src/mplacas, tests/, migrations/, scripts/). Define o gate de qualidade obrigatório antes de considerar qualquer tarefa de código concluída — ruff, mypy e pytest precisam passar limpos.
---

# Gate de qualidade Python — Mplacas

## Regra crítica

Sempre que este agente editar, criar ou apagar um arquivo `.py`, ele **MUST** rodar o
ciclo de CI completo antes de reportar a tarefa como concluída. O agente **NEVER**
encerra uma tarefa com Mypy, Ruff ou Pytest falhando — nem com a justificativa de que
"a falha é pré-existente" sem antes confirmar isso rodando o mesmo comando no `HEAD`
anterior à mudança.

## Comandos exatos (verificados em `.github/workflows/ci.yml` e `pyproject.toml`)

```bash
ruff check .
mypy
pytest -q
```

Não adicione `src/` a nenhum desses comandos — o projeto configura os alvos via
`pyproject.toml` (`[tool.mypy] packages = ["mplacas"]`, `[tool.pytest.ini_options]
pythonpath = ["src"]`). `mypy src/` ou `pytest tests/` mudam a resolução de imports e
podem mascarar ou inventar erros que não existem no comando real do CI.

## Passos

1. Após a última edição em um arquivo `.py`, rode os três comandos acima, nessa ordem
   (ruff é o mais rápido de falhar, pytest o mais lento).
2. Se `ruff check .` falhar: corrija o problema reportado. `ruff --fix` é aceitável só
   para findings mecânicos (imports, formatação) — nunca use para silenciar um warning
   de lógica sem entender a causa.
3. Se `mypy` falhar: **CRITICAL** — o agente NÃO tem permissão para encerrar a tarefa
   com erros de tipo pendentes. Não é aceitável adicionar `# type: ignore` para
   contornar o erro a menos que o próprio erro seja um falso positivo confirmado (ex:
   limitação conhecida de stub de biblioteca) — e nesse caso o ignore deve vir com o
   código do erro (`# type: ignore[attr-defined]`), nunca um ignore genérico.
4. Se `pytest -q` falhar: rode apenas o teste relacionado à mudança primeiro
   (`pytest -q tests/test_x.py -k nome_do_caso`) para iterar rápido, mas a suíte
   completa **MUST** passar antes de considerar a tarefa concluída — este projeto tem
   histórico de módulos com efeitos colaterais entre testes.
5. Se a mudança tocou em `src/mplacas/reports/export/*`, rode também os golden tests
   explicitamente (`test_report_exporter_golden.py`) — regressões nesse módulo não
   sempre aparecem como falha óbvia, podem só mudar bytes do PDF/XLSX gerado.

## Escopo de teste ao editar um módulo específico

Ao tocar em um módulo, rode pelo menos os testes do mesmo nome/área antes da suíte
completa, para não esperar o ciclo inteiro a cada iteração:

| Módulo editado | Teste mínimo a rodar primeiro |
|---|---|
| `src/mplacas/reports/**` | `pytest -q -k report` |
| `src/mplacas/retention/**` | `pytest -q -k retention` |
| `src/mplacas/billing/**` | `pytest -q -k billing` |
| `src/mplacas/auth/**`, `organizations/**` | `pytest -q -k "auth or organization"` |
| `migrations/versions/**` | ver skill `alembic-migrations` |

Isso é um atalho de iteração, não substitui o passo 4 (suíte completa antes de
concluir).

## O que NÃO fazer

- Não marque uma tarefa como concluída com qualquer um dos três comandos falhando.
- Não rode os comandos com paths diferentes dos documentados aqui sem checar
  `pyproject.toml` primeiro — a config pode mudar.
- Não use `--no-verify` ou pule hooks de commit para contornar uma falha de CI.
