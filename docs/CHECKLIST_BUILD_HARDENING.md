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

- [x] **Dependabot do grupo `python-runtime` bumpa `pyproject.toml`, não o lockfile — gap
  detectado e corrigido nesta sessão (2026-08-03).** Ao mesclar o PR #76 (`chore(deps): bump the
  python-runtime group with 5 updates`), o diff tocou só `pyproject.toml`; `requirements.lock` e
  `requirements-dev.lock` continuaram pinados nas versões antigas
  (`reportlab==4.5.1`, `argon2-cffi==23.1.0`, `google-cloud-storage==2.19.0`, `mypy==1.20.2`,
  `editables==0.5`), então as 5 dependências não tinham sido atualizadas de fato em runtime/CI
  apesar do PR aparecer mesclado e verde. Regenerado com
  `pip-compile pyproject.toml --generate-hashes --strip-extras --allow-unsafe
  --upgrade-package <nome> --output-file=requirements.lock` (idem com `--extra dev` +
  `mypy`/`editables` para o dev-lock) — usar `--upgrade-package` por nome é necessário porque o
  pip-compile, por padrão, preserva os pins existentes que ainda satisfazem o range e não teria
  de fato bumpado nada. Resultado: `argon2-cffi==25.1.0`, `google-cloud-storage==3.13.0`,
  `reportlab==5.0.0`, `mypy==2.3.0`, `editables==0.6` (mais a transitiva nova `ast-serialize`
  trazida pelo mypy 2.3.0). Um teste de contrato (`test_supply_chain_contract.py:20`) tinha
  `editables==0.5` hardcoded e precisou ser atualizado junto. Validado com
  `pip install --dry-run --require-hashes` (hashes batem) e suíte completa: ruff limpo, mypy
  limpo (181 arquivos, já sob o próprio mypy 2.3.0), 631 testes passando/5 skipped — sem regressão
  do salto maior de mypy nem do reportlab (usado no exportador de PDF).
  **Risco residual, não automatizado:** nada no CI hoje detecta esse gap sozinho — se a próxima
  IA/sessão mesclar um PR do grupo `python-runtime` sem regenerar o lockfile em seguida, o mesmo
  problema se repete silenciosamente. Vale um hook de CI que falhe se o lockfile ficar atrás do
  `pyproject.toml` após merge do Dependabot.

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
| P1 (build reprodutível) | 2 | 0 | 0 |
| P2 (automação de guardrail) | 0 | 0 | 1 |

O único item pendente (`audit-costs.sh` manual) não é falha de segurança ativa (diferente do gap
de `organization_id` em `CHECKLIST_SAAS_MULTITENANCY.md`, que é P0) — é lacuna de maturidade
operacional, vale planejar, não tratar como incidente. O risco residual de automação do lockfile
(ver item acima) também não é urgente pelo mesmo motivo: sem o hook de CI, o gap só se repete se
alguém mesclar o próximo bump do grupo `python-runtime` sem regenerar o lockfile em seguida.

## PR #70 (Docker Python 3.12 → 3.14) — mantido em aberto deliberadamente

Analisado em 2026-08-03: CI falha por design em dois testes de contrato
(`test_dockerfile_uses_cloud_run_entrypoint_and_non_root_user`,
`test_images_and_actions_are_immutable`) que travam a versão/digest da imagem base — não é a
imagem 3.14 quebrando algo, é o guardrail de supply chain funcionando. Salto de duas versões
maiores (pula 3.13), e nenhum teste de CI de fato constrói/roda a aplicação sob 3.14 — só valida
o texto do `Dockerfile`. Não mesclar sem antes: atualizar o digest fixado, validar compatibilidade
real de todas as dependências (lockfile) com 3.14, e rodar a suíte completa numa imagem construída
de fato sob 3.14.
