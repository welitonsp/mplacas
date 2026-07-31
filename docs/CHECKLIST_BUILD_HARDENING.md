# Checklist de remediação — Hardening de build e guardrails operacionais

Última atualização: 2026-07-30 (sessão 1)
Base: `origin/main` em `9a1c17c`
Origem: revisão de um relatório externo sobre o projeto ("Princípios de Confiabilidade",
"Guardrails GCP", "Regra de Entrega"), auditado item a item contra o código atual. A maioria das
premissas do relatório foi confirmada; os itens abaixo são as lacunas reais que sobraram dessa
auditoria — não vulnerabilidades novas, mas gaps de reprodutibilidade e automação.

Legenda: `[x]` concluído, `[~]` parcial, `[ ]` pendente.

## P1 — Build reprodutível

- [ ] **Sem lockfile de dependências.** Confirmado: não existe `requirements.txt` com hashes,
  `poetry.lock` nem `uv.lock` no repo. `pyproject.toml` declara ranges (`fastapi>=0.115,<1` etc.),
  e o `Dockerfile:15-16` roda `pip install .` sem pin exato nem verificação de hash. Duas builds
  em datas diferentes podem instalar versões de dependência diferentes dentro do range permitido —
  quebra a premissa de build reprodutível para uma imagem que vai para produção via Cloud Run.
  Ação: gerar lockfile (`pip-compile`, `uv lock`, ou equivalente) e usar no `Dockerfile` em vez de
  `pip install .` direto contra `pyproject.toml`.

## P2 — Automação de guardrail de custo/infra

- [ ] **`audit-costs.sh` é um guardrail real mas manual.** Confirmado: o script
  (`infra/gcp/audit-costs.sh:67-99`) falha explicitamente (`fail_if_output`) se existir Cloud SQL,
  Compute Engine ou Load Balancer com nome `~mplacas` — é enforcement de verdade, não só ausência
  de script de provisionamento. Porém só está documentado como comando manual em
  `docs/runbook-producao.md`; não roda em CI nem em Cloud Scheduler. É controle detectivo, não
  preventivo — infra paralela criada por engano só é pega na próxima execução manual. Ação:
  avaliar agendar `audit-costs.sh` via Cloud Scheduler + Cloud Run Job (mesmo padrão já usado para
  outros jobs do projeto) para virar controle contínuo.

## Resumo

| Categoria | Concluídos | Parciais | Pendentes |
|---|---:|---:|---:|
| P1 (build reprodutível) | 0 | 0 | 1 |
| P2 (automação de guardrail) | 0 | 0 | 1 |

Nenhum dos dois itens é uma falha de segurança ativa (diferente do gap de `organization_id` em
`CHECKLIST_SAAS_MULTITENANCY.md`, que é P0). São lacunas de maturidade operacional — vale planejar,
não tratar como incidente.
