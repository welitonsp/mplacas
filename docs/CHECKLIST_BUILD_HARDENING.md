# Checklist de remediação — Hardening de build e guardrails operacionais

Última atualização: 2026-08-03 (sessão 2)
Base: `origin/main` em `9a1c17c` (sessão 1); reconciliado em `6062530` (sessão 2).
Origem: revisão de um relatório externo sobre o projeto ("Princípios de Confiabilidade",
"Guardrails GCP", "Regra de Entrega"), auditado item a item contra o código atual. A maioria das
premissas do relatório foi confirmada; os itens abaixo são as lacunas reais que sobraram dessa
auditoria — não vulnerabilidades novas, mas gaps de reprodutibilidade e automação.

Legenda: `[x]` concluído, `[~]` parcial, `[ ]` pendente.

## P1 — Build reprodutível

- [x] **Lockfile de dependências criado e enforced.** Resolvido pelo P2-03 do ciclo BIG TECH
  (`AUDITORIA_BIG_TECH_2026-08-01.md`, ver `docs/SUPPLY_CHAIN_POLICY.md:5`): `requirements.lock`
  (runtime) e `requirements-dev.lock` (+ extra `dev`) gerados via `pip-compile --generate-hashes`.
  `Dockerfile:16` e `.github/workflows/ci.yml:22,152` instalam com
  `pip install --require-hashes -r requirements*.lock`, e `-e .` entra com `--no-deps` — ou seja,
  o range em `pyproject.toml` **não** controla a versão instalada de fato; o lockfile é a única
  fonte de verdade para o build. Este checklist (sessão 1, 2026-07-30) estava desatualizado sobre
  isso; reconciliado nesta sessão.

- [ ] **Dependabot do grupo `python-runtime` bumpa `pyproject.toml`, não o lockfile — merge sem
  efeito real no build.** Confirmado ao mesclar o PR #76 (`chore(deps): bump the python-runtime
  group with 5 updates`, 2026-08-03): o diff tocou só `pyproject.toml` (5 ranges alterados —
  reportlab, argon2-cffi, google-cloud-storage, editables, mypy). `requirements.lock` e
  `requirements-dev.lock` continuam pinados nas versões antigas (`reportlab==4.5.1`,
  `argon2-cffi==23.1.0`, `google-cloud-storage==2.19.0`, `mypy==1.20.2`, `editables==0.5`) — como
  o build instala com `--require-hashes` a partir do lockfile, essas 5 dependências **não foram
  atualizadas de fato** em runtime nem em CI, apesar do PR aparecer como mesclado e verde.
  Diferente do grupo `frontend` (PR #75), cujo Dependabot regenerou `package-lock.json`
  automaticamente (3122 linhas alteradas) — o ecossistema npm faz isso nativamente, o pip-compile
  não. Ação: após qualquer merge do grupo `python-runtime`, regenerar os lockfiles com os comandos
  já documentados em `SUPPLY_CHAIN_POLICY.md:24-27`
  (`pip-compile pyproject.toml --generate-hashes --strip-extras --allow-unsafe
  --output-file=requirements.lock`, idem com `--extra dev` para o dev-lock), rodar o
  `--dry-run --require-hashes` de verificação, e só então considerar a dependência de fato
  atualizada. Vale considerar automatizar esse passo (hook de CI que falha se o lockfile ficar
  atrás do `pyproject.toml` após um merge do Dependabot) para não repetir este gap.

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
| P1 (build reprodutível) | 1 | 0 | 1 |
| P2 (automação de guardrail) | 0 | 0 | 1 |

Nenhum item pendente é uma falha de segurança ativa (diferente do gap de `organization_id` em
`CHECKLIST_SAAS_MULTITENANCY.md`, que é P0). O item de lockfile-desatualizado-pelo-Dependabot é
importante mas não urgente: as versões antigas continuam hash-pinadas e instaláveis normalmente,
só não recebem os bumps que os PRs aparentam entregar. São lacunas de maturidade operacional —
vale planejar, não tratar como incidente.

## PR #70 (Docker Python 3.12 → 3.14) — mantido em aberto deliberadamente

Analisado em 2026-08-03: CI falha por design em dois testes de contrato
(`test_dockerfile_uses_cloud_run_entrypoint_and_non_root_user`,
`test_images_and_actions_are_immutable`) que travam a versão/digest da imagem base — não é a
imagem 3.14 quebrando algo, é o guardrail de supply chain funcionando. Salto de duas versões
maiores (pula 3.13), e nenhum teste de CI de fato constrói/roda a aplicação sob 3.14 — só valida
o texto do `Dockerfile`. Não mesclar sem antes: atualizar o digest fixado, validar compatibilidade
real de todas as dependências (lockfile) com 3.14, e rodar a suíte completa numa imagem construída
de fato sob 3.14.
